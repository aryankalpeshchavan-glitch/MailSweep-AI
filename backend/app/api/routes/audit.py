"""Audit trail browsing (owner-scoped, newest first)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", summary="Your audit trail")
def list_audit(
    event_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    query = db.query(AuditLog).filter(AuditLog.user_id == user.id)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type.upper())
    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "object_type": e.object_type,
                "object_id": e.object_id,
                "detail": e.detail,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
