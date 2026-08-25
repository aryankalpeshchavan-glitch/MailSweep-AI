"""Google OAuth 2.0 client (Authorization Code + offline access).

Deliberately thin and hand-rolled on top of ``httpx`` instead of hiding behind
a large SDK flow object:

* every outbound request is visible in ONE module,
* tests mock exactly one seam (:func:`_post_form`),
* no implicit token storage - callers decide persistence/encryption.

Security notes
--------------
* The ``state`` parameter is signed HMAC (see app.core.security) - the callback
  rejects forged/stale/expired states before touching the network.
* ``id_token`` claims are parsed WITHOUT signature verification. This is
  compliant for the code flow: the token arrives over TLS directly from
  Google's token endpoint in exchange for our confidential-client secret, per
  OIDC Core §3.1.3.7. (If this ever moves to implicit/hybrid flows, add JWKS
  verification.)
"""

from __future__ import annotations

import base64
import json
import logging
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"

#: Rationale per docs/ADR-0004-gmail-scopes.md
OIDC_SCOPES = ("openid", "email", "profile")
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


def requested_scopes() -> list[str]:
    return [*OIDC_SCOPES, GMAIL_MODIFY_SCOPE]


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    """Consent-screen URL. offline access => refresh token; consent => re-issue."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(requested_scopes()),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


def _post_form(
    url: str, data: dict, *, timeout: float = 15.0, ok_statuses: tuple[int, ...] = (200,)
) -> dict:
    """Single HTTP seam - the ONLY place this module touches the network."""
    try:
        response = httpx.post(url, data=data, timeout=timeout)
    except httpx.HTTPError as exc:
        logger.warning("google oauth http failure", extra={"event": "oauth_http_error"})
        raise ExternalServiceError("Could not reach Google's OAuth service.") from exc

    if response.status_code not in ok_statuses:
        # Provider error codes (e.g. 'invalid_grant') are safe identifiers;
        # raw bodies may contain PII/tokens and are never surfaced or logged.
        try:
            error_code = response.json().get("error", "unknown_error")
        except ValueError:
            error_code = "unparseable_response"
        logger.warning(
            "google oauth rejected request",
            extra={"event": "oauth_provider_error", "provider_error": error_code},
        )
        raise ExternalServiceError(f"Google rejected the OAuth request ({error_code}).")

    payload = response.json()
    if "error" in payload:
        raise ExternalServiceError(f"Google OAuth error ({payload['error']}).")
    return payload


def exchange_authorization_code(*, code: str, settings: Settings) -> dict:
    """Swap the authorization code for tokens (called once, on callback)."""
    return _post_form(
        TOKEN_ENDPOINT,
        {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.resolved_google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )


def refresh_access_token(*, refresh_token: str, settings: Settings) -> dict:
    return _post_form(
        TOKEN_ENDPOINT,
        {
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
    )


def revoke_token(token: str) -> None:
    """Best-effort grant revocation. 'Already revoked' (400) counts as success."""
    _post_form(REVOKE_ENDPOINT, {"token": token}, timeout=10.0, ok_statuses=(200, 400))


def decode_id_token_payload(id_token: str) -> dict:
    """Extract unverified claims from a JWT-shaped id_token (see docstring)."""
    try:
        _, payload_b64, _ = id_token.split(".")
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return claims if isinstance(claims, dict) else {}
    except (ValueError, json.JSONDecodeError):
        return {}
