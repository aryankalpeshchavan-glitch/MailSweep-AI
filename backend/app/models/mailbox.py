"""Mailbox, email metadata and grouping models.

Privacy note (ADR-0006): these tables intentionally have NO column capable of
holding an email body. Subjects are truncated to 500 chars. This is enforced
by the schema itself, not just by convention.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EmailCategory
from app.models.user import User  # noqa: F401 - registers mapper chain

_SUBJECT_MAX_LEN = 500


class Mailbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mailboxes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    google_email_address: Mapped[str] = mapped_column(String(320))
    history_id: Mapped[str | None] = mapped_column(String(64))
    last_analysis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_messages_cached: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship()
    messages: Mapped[list[EmailMessage]] = relationship(
        back_populates="mailbox", cascade="all, delete-orphan", passive_deletes=True,
    )


class EmailMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "gmail_message_id", name="uq_gmail_message_per_mailbox"),
        Index("ix_email_messages_mailbox_received", "mailbox_id", "received_at"),
        Index("ix_email_messages_mailbox_domain", "mailbox_id", "sender_domain"),
    )

    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(64))
    gmail_thread_id: Mapped[str | None] = mapped_column(String(64))

    sender_email: Mapped[str | None] = mapped_column(String(320))
    sender_name: Mapped[str | None] = mapped_column(String(255))
    #: Denormalized for fast grouping/filtering; derived from sender_email.
    sender_domain: Mapped[str | None] = mapped_column(String(255))

    subject: Mapped[str | None] = mapped_column(String(_SUBJECT_MAX_LEN))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    size_estimate: Mapped[int | None] = mapped_column(Integer)

    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    is_important: Mapped[bool] = mapped_column(Boolean, default=False)
    #: List-Unsubscribe header present => strong bulk-mail signal.
    has_list_unsubscribe: Mapped[bool] = mapped_column(Boolean, default=False)
    label_ids: Mapped[list] = mapped_column(JSON, default=list)

    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_groups.id", ondelete="SET NULL")
    )

    #: String-based targets avoid circular imports; mappers are configured
    #: once app.models.__init__ has imported every module.
    classification: Mapped[Classification | None] = relationship(  # noqa: F821
        back_populates="message", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )
    recommendation: Mapped[Recommendation | None] = relationship(  # noqa: F821
        back_populates="message", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )

    mailbox: Mapped[Mailbox] = relationship(back_populates="messages")


class EmailGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Deterministic cluster of similar messages (sender/pattern/category)."""

    __tablename__ = "email_groups"
    __table_args__ = (UniqueConstraint("mailbox_id", "group_key", name="uq_group_key_per_mailbox"),)

    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True
    )
    #: Stable hash of the grouping signals; recomputation-safe.
    group_key: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(255))
    primary_sender_domain: Mapped[str | None] = mapped_column(String(255))
    primary_category: Mapped[EmailCategory | None] = mapped_column(String(48))
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    first_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sample_subjects: Mapped[list] = mapped_column(JSON, default=list)
