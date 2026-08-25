"""Cleanup plan lifecycle: preview -> approval -> Trash execution -> ledger.

* Preview snapshots pending MOVE_TO_TRASH recommendations into an immutable
  per-message ledger. It NEVER touches Gmail.
* Approval is an atomic ``UPDATE ... WHERE status='PENDING_APPROVAL'``; a
  losing concurrent approver changes zero rows and gets a conflict.
* Execution flips APPROVED->EXECUTING under the same guard, then processes
  items one-by-one, committing after each - resumable, and Gmail receives at
  most one trash call per ledger row.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.auth.service import record_event
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.base import utcnow
from app.gmail.client import GmailClientProtocol
from app.models import (
    CleanupPlan,
    CleanupPlanItem,
    EmailMessage,
    Mailbox,
    Recommendation,
    User,
)
from app.models.enums import AuditEvent, CleanupPlanItemStatus, CleanupPlanStatus

logger = logging.getLogger(__name__)


def create_plan_preview(
    db: Session,
    *,
    user: User,
    recommendation_ids: list[str],
    idempotency_key: str | None = None,
    max_messages: int = 10_000,
) -> CleanupPlan:
    """Snapshot selected pending trash recommendations into a new plan."""
    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one_or_none()
    if mailbox is None:
        raise ValidationAppError("No analyzed mailbox connected to this account.")

    unique_ids = [
        uuid.UUID(str(r)) for r in dict.fromkeys(recommendation_ids)
    ]
    if not unique_ids:
        raise ValidationAppError("Select at least one recommendation.")
    if len(unique_ids) > max_messages:
        raise ValidationAppError(
            f"Selection exceeds the {max_messages}-message limit for one plan."
        )

    rows = (
        db.query(Recommendation, EmailMessage)
        .join(EmailMessage, Recommendation.message_id == EmailMessage.id)
        .filter(
            Recommendation.id.in_(unique_ids),
            Recommendation.mailbox_id == mailbox.id,
            Recommendation.action == "MOVE_TO_TRASH",
            Recommendation.status == "pending",
        )
        .all()
    )
    missing = len(unique_ids) - len(rows)
    if missing:
        raise NotFoundError(
            f"{missing} recommendation(s) not found, not pending, or not trash candidates."
        )

    if idempotency_key:
        existing = (
            db.query(CleanupPlan)
            .filter_by(user_id=user.id, idempotency_key=idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            return existing

    plan = CleanupPlan(
        user_id=user.id,
        mailbox_id=mailbox.id,
        status=CleanupPlanStatus.PENDING_APPROVAL.value,
        message_count=len(rows),
        idempotency_key=idempotency_key,
    )
    db.add(plan)
    db.flush()

    seen: set = set()
    for _recommendation, message in rows:
        if message.id in seen:
            continue
        seen.add(message.id)
        db.add(
            CleanupPlanItem(
                plan_id=plan.id,
                message_id=message.id,
                gmail_message_id=message.gmail_message_id,
                subject_snapshot=message.subject,
                sender_snapshot=message.sender_email,
                action="MOVE_TO_TRASH",
            )
        )
    plan.message_count = len(seen)
    db.commit()

    record_event(
        db, event_type=AuditEvent.CLEANUP_PREVIEW_CREATED, user_id=user.id,
        object_type="cleanup_plan", object_id=str(plan.id),
        detail={"messages": plan.message_count},
    )
    return plan


def _owned_plan(db: Session, user: User, plan_id: str) -> CleanupPlan:
    plan = (
        db.query(CleanupPlan)
        .filter_by(id=uuid.UUID(str(plan_id)), user_id=user.id)
        .one_or_none()
    )
    if plan is None:
        raise NotFoundError("Cleanup plan not found.")
    return plan


def approve_plan(db: Session, *, user: User, plan_id: str) -> CleanupPlan:
    """Atomically move PENDING_APPROVAL -> APPROVED. Idempotency gate."""
    plan = _owned_plan(db, user, plan_id)
    updated = (
        db.query(CleanupPlan)
        .filter(
            CleanupPlan.id == plan.id,
            CleanupPlan.user_id == user.id,
            CleanupPlan.status == CleanupPlanStatus.PENDING_APPROVAL.value,
        )
        .update({"status": CleanupPlanStatus.APPROVED.value, "approved_at": utcnow()})
    )
    db.commit()
    if updated == 0:
        raise ConflictError(
            f"Plan is not awaiting approval (current status: {plan.status})."
        )
    db.refresh(plan)
    record_event(
        db, event_type=AuditEvent.CLEANUP_APPROVED, user_id=user.id,
        object_type="cleanup_plan", object_id=str(plan.id),
        detail={"messages": plan.message_count},
    )
    return plan


def cancel_plan(db: Session, *, user: User, plan_id: str) -> CleanupPlan:
    """Only pre-approval plans can be cancelled."""
    plan = _owned_plan(db, user, plan_id)
    updated = (
        db.query(CleanupPlan)
        .filter(
            CleanupPlan.id == plan.id,
            CleanupPlan.user_id == user.id,
            CleanupPlan.status == CleanupPlanStatus.PENDING_APPROVAL.value,
        )
        .update({"status": CleanupPlanStatus.CANCELLED.value, "cancelled_at": utcnow()})
    )
    db.commit()
    if updated == 0:
        raise ConflictError(f"Plan cannot be cancelled (current status: {plan.status}).")
    db.refresh(plan)
    record_event(
        db, event_type=AuditEvent.CLEANUP_CANCELLED, user_id=user.id,
        object_type="cleanup_plan", object_id=str(plan.id),
    )
    return plan


def execute_approved_plan(
    db: Session, *, plan_id: str, gmail: GmailClientProtocol
) -> CleanupPlan:
    """Trash each ledger row once; per-item outcomes committed immediately."""
    plan_pk = uuid.UUID(str(plan_id))
    plan = db.get(CleanupPlan, plan_pk)
    if plan is None:
        raise NotFoundError("Cleanup plan not found.")

    claimed = (
        db.query(CleanupPlan)
        .filter(
            CleanupPlan.id == plan_pk,
            CleanupPlan.status == CleanupPlanStatus.APPROVED.value,
        )
        .update({
            "status": CleanupPlanStatus.EXECUTING.value,
            "execution_started_at": utcnow(),
        })
    )
    db.commit()
    if claimed == 0:
        raise ConflictError(f"Plan is not executable (current status: {plan.status}).")
    db.refresh(plan)

    record_event(
        db, event_type=AuditEvent.CLEANUP_EXECUTION_STARTED, user_id=plan.user_id,
        object_type="cleanup_plan", object_id=str(plan.id),
        detail={"messages": plan.message_count},
    )

    trashed = failed = 0
    errors: list[dict] = []
    items = (
        db.query(CleanupPlanItem)
        .filter_by(plan_id=plan.id, item_status=CleanupPlanItemStatus.PENDING.value)
        .all()
    )
    for item in items:
        try:
            gmail.trash_message(item.gmail_message_id)
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal to siblings
            item.item_status = CleanupPlanItemStatus.FAILED.value
            item.failure_reason = f"{type(exc).__name__}: {exc}"[:500]
            failed += 1
            errors.append({"gmail_message_id": item.gmail_message_id,
                           "reason": type(exc).__name__})
        else:
            item.item_status = CleanupPlanItemStatus.TRASHED.value
            trashed += 1
        item.executed_at = utcnow()
        db.commit()

    plan.status = _final_status(trashed, failed)
    plan.completed_at = utcnow()
    plan.failure_summary = None if not errors else {"failed": failed, "errors": errors[:50]}
    db.commit()
    record_event(
        db,
        event_type=(
            AuditEvent.CLEANUP_FAILED
            if plan.status == CleanupPlanStatus.FAILED.value
            else AuditEvent.CLEANUP_COMPLETED
        ),
        user_id=plan.user_id,
        object_type="cleanup_plan",
        object_id=str(plan.id),
        detail={"trashed": trashed, "failed": failed},
    )
    logger.info(
        "cleanup plan finished",
        extra={"event": "cleanup_finished", "plan_id": str(plan.id),
               "trashed": trashed, "failed": failed},
    )
    return plan


def _final_status(trashed: int, failed: int) -> str:
    if failed == 0:
        return CleanupPlanStatus.COMPLETED.value
    if trashed == 0:
        return CleanupPlanStatus.FAILED.value
    return CleanupPlanStatus.COMPLETED_WITH_FAILURES.value

