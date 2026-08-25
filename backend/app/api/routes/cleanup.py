"""Cleanup plan endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.cleanup.service import (
    approve_plan,
    cancel_plan,
    create_plan_preview,
)
from app.core.config import Settings
from app.db.session import get_db
from app.models import CleanupPlan, CleanupPlanItem, User
from app.models.enums import CleanupPlanStatus
from app.workers.dispatcher import dispatch_cleanup

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])


class PlanPreviewRequest(BaseModel):
    recommendation_ids: list[uuid.UUID] = Field(min_length=1, max_length=10_000)
    idempotency_key: str | None = Field(default=None, max_length=64)


class PlanItemOut(BaseModel):
    message_id: uuid.UUID
    gmail_message_id: str
    subject_snapshot: str | None
    sender_snapshot: str | None
    item_status: str
    failure_reason: str | None


class PlanOut(BaseModel):
    id: uuid.UUID
    status: str
    message_count: int
    created_at: datetime
    approved_at: datetime | None
    completed_at: datetime | None
    failure_summary: dict | None
    items: list[PlanItemOut] = []


def _plan_out(db: Session, plan: CleanupPlan, *, include_items: bool = True) -> dict:
    body = {
        "id": str(plan.id),
        "status": str(plan.status),
        "message_count": plan.message_count,
        "created_at": plan.created_at.isoformat(),
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        "failure_summary": plan.failure_summary,
    }
    if include_items:
        body["items"] = [
            {
                "message_id": str(item.message_id),
                "gmail_message_id": item.gmail_message_id,
                "subject_snapshot": item.subject_snapshot,
                "sender_snapshot": item.sender_snapshot,
                "item_status": str(item.item_status),
                "failure_reason": item.failure_reason,
            }
            for item in db.query(CleanupPlanItem).filter_by(plan_id=plan.id).all()
        ]
    return body


@router.post(
    "/preview",
    status_code=201,
    summary="Create a cleanup plan preview (touches nothing on Gmail)",
    description=(
        "Snapshots the selected pending MOVE_TO_TRASH recommendations into an "
        "immutable plan awaiting approval."
    ),
)
def post_preview(
    payload: PlanPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings: Settings = request.app.state.settings
    plan = create_plan_preview(
        db,
        user=user,
        recommendation_ids=[str(r) for r in payload.recommendation_ids],
        idempotency_key=payload.idempotency_key,
        max_messages=settings.MAX_MESSAGES_PER_ANALYSIS,
    )
    return _plan_out(db, plan)


@router.get("/plans", summary="List the caller's cleanup plans (newest first)")
def list_plans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: CleanupPlanStatus | None = Query(None, alias="status"),
) -> list[dict]:
    query = db.query(CleanupPlan).filter_by(user_id=user.id)
    if status_filter is not None:
        query = query.filter_by(status=status_filter.value)
    plans = query.order_by(CleanupPlan.created_at.desc()).limit(50).all()
    return [_plan_out(db, plan, include_items=False) for plan in plans]


@router.get("/plans/{plan_id}", summary="Inspect one plan including its item ledger")
def get_plan(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    plan = db.query(CleanupPlan).filter_by(id=plan_id, user_id=user.id).one_or_none()
    if plan is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Cleanup plan not found.")
    return _plan_out(db, plan)


@router.post(
    "/plans/{plan_id}/approve",
    summary="Approve the plan and dispatch Trash execution",
    responses={409: {"description": "Plan already processed"}},
)
def post_approve(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    plan = approve_plan(db, user=user, plan_id=str(plan_id))
    task_ref = dispatch_cleanup(str(plan.id))
    return {
        "id": str(plan.id),
        "status": str(plan.status),
        "dispatched_to": task_ref,
        "message_count": plan.message_count,
    }


@router.post("/plans/{plan_id}/cancel", summary="Cancel a plan that is still awaiting approval")
def post_cancel(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    plan = cancel_plan(db, user=user, plan_id=str(plan_id))
    return {"id": str(plan.id), "status": str(plan.status)}
