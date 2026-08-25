"""User, session and OAuth-connection models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCTimestamp, UUIDPrimaryKeyMixin
from app.models.enums import OAuthStatus


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    #: Verified address from Google; also our login identifier.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))

    #: Soft-delete timestamp. Personal data purge happens asynchronously;
    #: rows are never hard-deleted mid-request (keeps audit trails coherent).
    deleted_at: Mapped[datetime | None] = mapped_column(UTCTimestamp())

    oauth_connection: Mapped[OAuthConnection | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
    )


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Server-side session. Only the SHA-256 hash of the cookie value is stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCTimestamp())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCTimestamp())

    user: Mapped[User] = relationship(back_populates="sessions")

    @property
    def is_active(self) -> bool:
        from app.db.base import utcnow

        return self.revoked_at is None and self.expires_at > utcnow()


class OAuthConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Gmail account per MailSweep account (schema tolerates more later).

    Tokens are Fernet ciphertext (see app.core.security); plaintext never
    touches this table or the logs.
    """

    __tablename__ = "oauth_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="google")
    google_sub: Mapped[str] = mapped_column(String(64), unique=True)
    google_email: Mapped[str] = mapped_column(String(320))

    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCTimestamp())
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCTimestamp())

    status: Mapped[OAuthStatus] = mapped_column(
        String(16), default=OAuthStatus.ACTIVE, index=True
    )
    #: Truncated, secret-free description of the last provider-side failure.
    last_error: Mapped[str | None] = mapped_column(String(512))
    connected_at: Mapped[datetime] = mapped_column(UTCTimestamp())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCTimestamp())

    user: Mapped[User] = relationship(back_populates="oauth_connection")
