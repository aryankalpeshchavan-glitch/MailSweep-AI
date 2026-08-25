"""Authentication endpoints: status, logout, Google OAuth flow, disconnect."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    clear_session_cookie,
    get_current_user,
    get_current_user_optional,
    set_session_cookie,
)
from app.auth import google_oauth
from app.auth.service import (
    create_session,
    disconnect_google_account,
    record_event,
    revoke_session,
    upsert_oauth_identity,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import sign_oauth_state, verify_oauth_state
from app.db.session import get_db
from app.models import User
from app.models.enums import AuditEvent, OAuthStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Relative-path guard: blocks `https://evil.com`, `//evil.com`, `\evil`, etc.
_SAFE_REDIRECT = re.compile(r"^/[^/\\]")


def _frontend_base(settings: Settings) -> str:
    """Primary frontend origin; falls back to this backend's own base."""
    origins = settings.cors_allowed_origins
    return origins[0] if origins else settings.BASE_URL


@router.get(
    "/status",
    summary="Current authentication + Gmail connection state",
    description="Anonymous-safe: returns `authenticated: false` instead of 401.",
)
def auth_status(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> dict:
    _ = request, db
    if user is None:
        return {"authenticated": False}

    connection = user.oauth_connection
    gmail: dict = {
        "connected": bool(connection and connection.status == OAuthStatus.ACTIVE),
        "email": connection.google_email if connection else None,
        "status": str(connection.status) if connection else None,
        "connected_at": connection.connected_at.isoformat() if connection else None,
        "granted_scopes": (connection.scope or "").split() if connection else [],
    }
    return {
        "authenticated": True,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        },
        "gmail_connection": gmail,
    }


@router.post(
    "/logout",
    status_code=204,
    summary="Revoke the current session",
)
def logout(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    raw_token = request.cookies.get("mailsweep_session")
    if raw_token:
        revoke_session(db, raw_token)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get(
    "/google/login",
    summary="Start Google OAuth (redirects to Google's consent screen)",
)
def google_login(
    request: Request,
    redirect_to: str = Query("/", description="Relative in-app path after login."),
) -> Response:
    settings: Settings = request.app.state.settings
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise AppError(
            "Google OAuth is not configured on this server.",
            code="oauth_not_configured", status_code=503,
        )

    # Open-redirect defense: only same-site absolute paths survive.
    safe_path = redirect_to if _SAFE_REDIRECT.match(redirect_to) else "/"
    state = sign_oauth_state(
        {"redirect_to": safe_path}, secret_key=settings.effective_secret_key()
    )
    url = google_oauth.build_authorization_url(
        client_id=settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.resolved_google_redirect_uri,
        state=state,
    )
    return RedirectResponse(url, status_code=302)


@router.get(
    "/google/callback",
    summary="Google OAuth callback (browser lands here from Google)",
)
async def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
) -> Response:
    settings: Settings = request.app.state.settings

    if error:
        reason = (
            "Google sign-in was cancelled."
            if error == "access_denied"
            else f"OAuth error: {error}"
        )
        code = "consent_denied" if error == "access_denied" else "oauth_error"
        raise AppError(reason, code=code, status_code=400)

    payload = verify_oauth_state(state, secret_key=settings.effective_secret_key())
    if payload is None:
        raise AppError(
            "Invalid or expired OAuth state.", code="invalid_oauth_state", status_code=400
        )
    if not code:
        raise AppError(
            "Missing authorization code.", code="missing_authorization_code", status_code=400
        )

    tokens = google_oauth.exchange_authorization_code(code=code, settings=settings)

    claims = google_oauth.decode_id_token_payload(tokens.get("id_token", ""))
    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise AppError(
            "Google did not return an identity.",
            code="oauth_identity_missing",
            status_code=502,
        )
    if not claims.get("email_verified", False):
        raise AppError(
            "Google account email is not verified.",
            code="email_unverified",
            status_code=403,
        )

    user, connection = upsert_oauth_identity(
        db,
        sub=str(sub),
        email=str(email),
        display_name=claims.get("name"),
        avatar_url=claims.get("picture"),
        scope=tokens.get("scope"),
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        expires_in=int(tokens.get("expires_in", 3600)),
        secret_key=settings.effective_secret_key(),
    )
    raw_token = create_session(db, user_id=user.id, ttl_days=settings.SESSION_TTL_DAYS)
    record_event(
        db,
        event_type=AuditEvent.ACCOUNT_CONNECTED,
        user_id=user.id,
        object_type="oauth_connection",
        object_id=str(connection.id),
        detail={"scopes": (tokens.get("scope") or "").split()},
    )

    target = payload.get("redirect_to") or "/"
    if not isinstance(target, str) or not _SAFE_REDIRECT.match(target):
        target = "/"
    response = RedirectResponse(f"{_frontend_base(settings)}{target}", status_code=302)
    set_session_cookie(response, raw_token, settings)
    return response


@router.post(
    "/google/disconnect",
    status_code=204,
    summary="Disconnect Gmail: revoke grant, delete cached mailbox data & tokens",
)
def google_disconnect(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    settings: Settings = request.app.state.settings
    disconnect_google_account(
        db,
        user=user,
        secret_key=settings.effective_secret_key(),
        http_revoke=google_oauth.revoke_token,
    )
    record_event(
        db,
        event_type=AuditEvent.ACCOUNT_DISCONNECTED,
        user_id=user.id,
        object_type="user",
        object_id=str(user.id),
    )
    logger.info(
        "gmail disconnected",
        extra={"event": AuditEvent.ACCOUNT_DISCONNECTED.value},
    )
    return Response(status_code=204)


