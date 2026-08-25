"""User rule CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.service import record_event
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.session import get_db
from app.models import CleanupRule, User
from app.models.enums import AuditEvent, RuleKind
from app.rules.engine import _FIELD_OPS

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleCondition(BaseModel):
    field: str
    op: str
    value: str | int | float | bool


class RuleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: RuleKind
    match_all: bool = True
    conditions: list[RuleCondition] = Field(min_length=1, max_length=20)
    priority: int = 100


class RuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    match_all: bool | None = None
    conditions: list[RuleCondition] | None = Field(default=None, min_length=1, max_length=20)
    priority: int | None = None
    enabled: bool | None = None


def _validate_conditions(conditions: list[RuleCondition]) -> list[dict]:
    for condition in conditions:
        ops = _FIELD_OPS.get(condition.field)
        if ops is None or condition.op not in ops:
            raise ValidationAppError(
                f"Unsupported condition {condition.field!r} / op {condition.op!r}."
            )
    return [c.model_dump() for c in conditions]


@router.get("", summary="List the caller's rules (PROTECT first)")
def list_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    rules = (
        db.query(CleanupRule)
        .filter_by(user_id=user.id)
        .order_by(CleanupRule.kind.desc(), CleanupRule.priority.asc(), CleanupRule.created_at)
        .all()
    )
    return [
        {
            "id": str(r.id), "name": r.name, "kind": str(r.kind),
            "match_all": r.match_all, "conditions": r.conditions,
            "priority": r.priority, "enabled": bool(r.enabled),
        }
        for r in rules
    ]


@router.post("", status_code=201, summary="Create a rule")
def create_rule(
    payload: RuleCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    duplicate = (
        db.query(CleanupRule).filter_by(user_id=user.id, name=payload.name).one_or_none()
    )
    if duplicate is not None:
        raise ConflictError(f"A rule named '{payload.name}' already exists.")

    rule = CleanupRule(
        user_id=user.id,
        name=payload.name,
        kind=payload.kind.value,
        match_all=payload.match_all,
        conditions=_validate_conditions(payload.conditions),
        priority=payload.priority,
    )
    db.add(rule)
    db.commit()
    record_event(db, event_type=AuditEvent.RULE_CREATED, user_id=user.id,
                 object_type="cleanup_rule", object_id=str(rule.id))
    return {"id": str(rule.id), "name": rule.name, "kind": str(rule.kind)}


@router.put("/{rule_id}", summary="Update a rule")
def update_rule(
    rule_id: uuid.UUID,
    payload: RuleUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    rule = db.query(CleanupRule).filter_by(id=rule_id, user_id=user.id).one_or_none()
    if rule is None:
        raise NotFoundError("Rule not found.")
    if all(
        getattr(payload, f) is None
        for f in ("name", "match_all", "conditions", "priority", "enabled")
    ):
        raise ValidationAppError("At least one field to update is required.")
    if payload.name is not None:
        rule.name = payload.name
    if payload.match_all is not None:
        rule.match_all = payload.match_all
    if payload.conditions is not None:
        rule.conditions = _validate_conditions(payload.conditions)
    if payload.priority is not None:
        rule.priority = payload.priority
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    db.commit()
    record_event(db, event_type=AuditEvent.RULE_UPDATED, user_id=user.id,
                 object_type="cleanup_rule", object_id=str(rule.id))
    return {
        "id": str(rule.id), "name": rule.name,
        "kind": str(rule.kind), "enabled": bool(rule.enabled),
    }


@router.delete("/{rule_id}", status_code=204, summary="Delete a rule")
def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    rule = db.query(CleanupRule).filter_by(id=rule_id, user_id=user.id).one_or_none()
    if rule is None:
        raise NotFoundError("Rule not found.")
    db.delete(rule)
    db.commit()
    record_event(db, event_type=AuditEvent.RULE_DELETED, user_id=user.id,
                 object_type="cleanup_rule", object_id=str(rule_id))
