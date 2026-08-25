"""Session & identity persistence.

Sessions are opaque random tokens in an HttpOnly cookie; the database stores
only their SHA-256 hash. Revocation is instant (logout, disconnect, admin
action) because validity is a DB row, not an unforgeable blob.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.core.security import decrypt_text, encrypt_text, hash_session_token, new_session_token
from app.db.base import utcnow
from app.models import AuditLog, Mailbox, OAuthConnection, User, UserSession
from app.models.enums import OAuthStatus

logger = logging.getLogger(__name__)


def create_session(db: Session, *, user_id: str, ttl_days: int) -> str:
    """Persist a new session; returns the RAW token for the cookie."""
    raw_token = new_session_token()
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_session_token(raw_token),
            expires_at=utcnow() + timedelta(days=ttl_days),
        )
    )
    db.commit()
    return raw_token


def resolve_session(db: Session, raw_token: str | None) -> User | None:
    """Return the active user for a cookie value, or None. Never raises."""
    if not raw_token:
        return None
    row = db.query(UserSession).filter_by(token_hash=hash_session_token(raw_token)).one_or_none()
    if row is None or not row.is_active:
        return None
    user = row.user
    if user.deleted_at is not None:
        return None
    return user


def revoke_session(db: Session, raw_token: str) -> bool:
    row = db.query(UserSession).filter_by(token_hash=hash_session_token(raw_token)).one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = utcnow()
    db.commit()
    return True


def upsert_oauth_identity(
    db: Session,
    *,
    sub: str,
    email: str,
    display_name: str | None,
    avatar_url: str | None,
    scope: str | None,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    secret_key: bytes,
) -> tuple[User, OAuthConnection]:
    """Create-or-update the Google identity binding; store ENCRYPTED tokens."""
    connection = db.query(OAuthConnection).filter_by(google_sub=sub).one_or_none()

    if connection is None:
        # Match an existing (future: password-based) account by verified email.
        user = db.query(User).filter_by(email=email).one_or_none()
        if user is None:
            user = User(email=email, display_name=display_name, avatar_url=avatar_url)
            db.add(user)
            db.flush()
        elif user.deleted_at is not None:
            user.deleted_at = None  # re-activating a soft-deleted account
        connection = OAuthConnection(
            user_id=user.id,
            google_sub=sub,
            google_email=email,
            connected_at=utcnow(),
            status=OAuthStatus.ACTIVE,
        )
        db.add(connection)
        db.flush()
    else:
        user = connection.user

    user.display_name = display_name or user.display_name
    user.avatar_url = avatar_url or user.avatar_url

    connection.access_token_encrypted = encrypt_text(access_token, secret_key=secret_key)
    if refresh_token:  # Google omits it when consent isn't re-prompted
        connection.refresh_token_encrypted = encrypt_text(refresh_token, secret_key=secret_key)
    connection.scope = scope
    connection.token_expires_at = utcnow() + timedelta(seconds=expires_in)
    connection.status = OAuthStatus.ACTIVE
    connection.last_error = None

    db.commit()
    return user, connection


def disconnect_google_account(
    db: Session,
    *,
    user: User,
    secret_key: bytes,
    http_revoke=None,
) -> None:
    """Revoke the Google grant, purge mailbox data, neutralize stored tokens.

    ``http_revoke`` is injectable for tests. Revocation is BEST-EFFORT: if
    Google is unreachable we still delete our token copies - the local account
    must never remain usable because a third party was down.

    Cached mailbox metadata and everything hanging off it (messages, groups,
    classifications, recommendations, plans/items) is purged via cascade.
    User-authored rules/decisions are kept: they are configuration, not email
    data, and make reconnecting pleasant. Documented in README privacy table.
    """
    connection = user.oauth_connection
    if connection is None:
        return

    token_to_revoke: str | None = None
    for ciphertext in (connection.refresh_token_encrypted, connection.access_token_encrypted):
        if ciphertext:
            try:
                token_to_revoke = decrypt_text(ciphertext, secret_key=secret_key)
                break
            except ValueError:
                continue
    if token_to_revoke and http_revoke is not None:
        try:
            http_revoke(token_to_revoke)
        except Exception:  # noqa: BLE001 - see docstring: proceed regardless
            logger.warning(
                "grant revocation failed; local tokens deleted anyway",
                extra={"event": "oauth_revoke_incomplete"},
            )

    mailbox = db.query(Mailbox).filter_by(user_id=user.id).first()
    if mailbox is not None:
        db.delete(mailbox)

    connection.access_token_encrypted = None
    connection.refresh_token_encrypted = None
    connection.token_expires_at = None
    connection.scope = connection.scope  # keep record of what WAS granted
    connection.status = OAuthStatus.REVOKED
    connection.revoked_at = utcnow()
    connection.last_error = None

    db.commit()


def record_event(
    db: Session,
    *,
    event_type,
    user_id=None,
    object_type: str | None = None,
    object_id: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append one audit fact in its own transaction. Never raises upward."""
    rid = request_id_var.get()
    try:
        db.add(
            AuditLog(
                user_id=user_id,
                event_type=getattr(event_type, "value", str(event_type)),
                object_type=object_type,
                object_id=object_id,
                detail=detail or {},
                request_id=None if rid == "-" else rid,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - auditing must not break the main flow
        db.rollback()
        logger.exception("failed to persist audit event", extra={"event": "audit_write_failed"})


