"""Cleanup plans and their per-message execution ledger.

Safety model (spec §11/§37):

* A plan starts as PENDING_APPROVAL - a *preview*, touching nothing.
* Approval performs an atomic ``UPDATE ... WHERE status='PENDING_APPROVAL'``
  transition; a second approval attempt loses the race and returns conflict.
* Execution flips the plan to EXECUTING, then walks items one by one,
  recording per-item outcome. Gmail is called at most once per item row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class CleanupPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cleanup_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_plan_idempotency_per_user"),
        Index("ix_cleanup_plans_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String(32), default="PENDING_APPROVAL")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    #: Client-supplied dedup key for preview creation; execution idempotency
    #: comes from the status state machine, not from this column.
    idempotency_key: Mapped[str | None] = mapped_column(String(64))

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: {"trashed": n, "failed": m, "errors": [{"gmail_message_id":..., "reason":...}]}
    failure_summary: Mapped[dict | None] = mapped_column(JSON)

    items: Mapped[list[CleanupPlanItem]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", passive_deletes=True,
    )


class CleanupPlanItem(UUIDPrimaryKeyMixin, Base):
    """Immutable ledger row for one message inside one plan.

    Snapshots (gmail id / subject / sender) keep the audit trail meaningful
    even after the source metadata rows are deleted.
    """

    __tablename__ = "cleanup_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "message_id", name="uq_plan_item_message"),
        Index("ix_plan_items_plan_status", "plan_id", "item_status"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cleanup_plans.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"), index=True
    )

    gmail_message_id: Mapped[str] = mapped_column(String(64))
    subject_snapshot: Mapped[str | None] = mapped_column(String(500))
    sender_snapshot: Mapped[str | None] = mapped_column(String(320))

    action: Mapped[str] = mapped_column(String(24), default="MOVE_TO_TRASH")
    item_status: Mapped[str] = mapped_column(String(16), default="PENDING")
    failure_reason: Mapped[str | None] = mapped_column(String(512))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    plan: Mapped[CleanupPlan] = relationship(back_populates="items")
