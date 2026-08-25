"""Access-token lifecycle: ONE explicit, testable refresh path.

google-auth could auto-refresh inside its Credentials object, but that would
scatter silent network calls across the codebase and leave refreshed tokens
unpersisted. Instead: callers ask this module for a valid token; if it is near
expiry we refresh once, persist the new encrypted value, and return it.
The actual HTTP call goes through ``google_oauth._post_form`` (the same seam
the OAuth flow uses), so tests patch exactly one function.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.auth import google_oauth
from app.core.config import Settings
from app.core.errors import ExternalServiceError
from app.core.security import decrypt_text, encrypt_text
from app.db.base import utcnow
from app.models import User
from app.models.enums import OAuthStatus

logger = logging.getLogger(__name__)

#: Refresh this long before actual expiry to tolerate clock skew/in-flight work.
_REFRESH_MARGIN_SECONDS = 60


def get_valid_access_token(
    db: Session, *, user: User, secret_key: bytes, settings: Settings
) -> str:
    """Return a usable Gmail access token, refreshing + persisting if stale."""
    connection = user.oauth_connection
    if (
        connection is None
        or connection.status != OAuthStatus.ACTIVE
        or not connection.refresh_token_encrypted
        or not connection.access_token_encrypted
    ):
        raise ExternalServiceError(
            "Gmail is not connected (or the grant was lost). Reconnect the account.",
        )

    access_token = decrypt_text(connection.access_token_encrypted, secret_key=secret_key)

    expires_at = connection.token_expires_at
    still_valid = expires_at is not None and (expires_at - utcnow()).total_seconds() > (
        _REFRESH_MARGIN_SECONDS
    )
    if still_valid:
        return access_token

    logger.info("refreshing gmail access token", extra={"event": "token_refresh"})
    refresh_token = decrypt_text(connection.refresh_token_encrypted, secret_key=secret_key)
    try:
        tokens = google_oauth.refresh_access_token(refresh_token=refresh_token, settings=settings)
    except ExternalServiceError:
        connection.last_error = "Token refresh failed"
        db.commit()
        raise

    new_access = str(tokens["access_token"])
    connection.access_token_encrypted = encrypt_text(new_access, secret_key=secret_key)
    connection.token_expires_at = utcnow() + timedelta(
        seconds=int(tokens.get("expires_in", 3600))
    )
    connection.last_refreshed_at = utcnow()
    connection.last_error = None
    db.commit()
    return new_access
