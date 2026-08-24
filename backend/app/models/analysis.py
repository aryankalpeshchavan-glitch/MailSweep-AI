"""Analysis pipeline models: jobs, classifications, recommendations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AnalysisJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One full-mailbox analysis run. Progress is persisted so the API can
    poll meaningful state without touching the job queue."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (Index("ix_analysis_jobs_mailbox_status", "mailbox_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    messages_total: Mapped[int | None]
    messages_processed: Mapped[int] = mapped_column(Integer, default=0)

    error_code: Mapped[str | None] = mapped_column(String(64))
    #: Secret-free human summary; provider payloads never land here.
    error_message: Mapped[str | None] = mapped_column(String(512))

    dispatcher_task_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Classification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Latest classification per message (one row - upserted on re-analysis)."""

    __tablename__ = "classifications"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"), unique=True, index=True
    )
    category: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(8))  # rule | ai | user
    confidence: Mapped[float | None] = mapped_column(Float)
    risk: Mapped[str | None] = mapped_column(String(16))
    #: [{code: "...", detail: "..."}] - machine-readable explanation chain.
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    #: AI's free-text justification (subject-derived only, never bodies).
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    classifier_version: Mapped[str] = mapped_column(String(32))

    message: Mapped[EmailMessage] = relationship(back_populates="classification")  # noqa: F821


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Explainable per-message recommendation (confidence != risk!)."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_mailbox_action", "mailbox_id", "action"),
        Index("ix_recommendations_mailbox_status_risk", "mailbox_id", "status", "risk"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"), unique=True, index=True
    )
    #: Denormalized from message.mailbox_id to keep list endpoints fast.
    mailbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"))

    action: Mapped[str] = mapped_column(String(24))  # KEEP / MOVE_TO_TRASH / REVIEW
    confidence: Mapped[float] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    #: IDs of user rules that contributed, for transparent traceability.
    contributing_rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    #: pending | dismissed | applied | superseded
    status: Mapped[str] = mapped_column(String(16), default="pending")

    message: Mapped[EmailMessage] = relationship(back_populates="recommendation")  # noqa: F821
