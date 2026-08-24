"""User-defined rules and recorded decisions.

Rules are stored as declarative JSON condition lists, validated by Pydantic
schemas (app.schemas.rules) and evaluated deterministically by the rule
engine (app.rules.evaluator). The DB never interprets them.

Protection rules ALWAYS outrank cleanup rules regardless of priority -
priority only orders rules of the same kind.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CleanupRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cleanup_rules"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_rule_name_per_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))  # PROTECT | CLEANUP
    match_all: Mapped[bool] = mapped_column(Boolean, default=True)  # AND vs OR
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    #: Lower runs earlier within its kind. Protection always wins overall.
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class UserDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What the human chose for a message. Feeds future preference learning
    (spec §21) and gives the API an override surface."""

    __tablename__ = "user_decisions"
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_decision_per_message"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))  # KEEP | MOVE_TO_TRASH
    context: Mapped[str] = mapped_column(String(16), default="INDIVIDUAL")  # INDIVIDUAL | PLAN
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cleanup_plans.id", ondelete="SET NULL")
    )
