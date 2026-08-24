"""Append-only audit trail (spec §38).

* No ``updated_at``: rows are facts, not state.
* ``detail`` holds identifiers and counters ONLY - never subjects, bodies,
  tokens or secrets.
* Deleting a user nulls their id here but keeps the event history.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_event_created", "event_type", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(48))
    object_type: Mapped[str | None] = mapped_column(String(48))
    object_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
