"""Recommendation browsing endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import Classification, EmailMessage, Mailbox, Recommendation, User

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _base_query(db: Session, user: User):
    mailbox_id = db.query(Mailbox.id).filter_by(user_id=user.id).scalar()
    if mailbox_id is None:
        return None
    return (
        db.query(Recommendation, EmailMessage, Classification)
        .join(EmailMessage, Recommendation.message_id == EmailMessage.id)
        .outerjoin(Classification, Classification.message_id == EmailMessage.id)
        .filter(
            Recommendation.mailbox_id == mailbox_id,
            Recommendation.status == "pending",
        )
    )


@router.get("", summary="Browse pending recommendations (paginated, filterable)")
def list_recommendations(
    action: str | None = Query(None),
    risk: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    query = _base_query(db, user)
    if query is None:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}
    if action:
        query = query.filter(Recommendation.action == action.upper())
    if risk:
        query = query.filter(Recommendation.risk == risk.upper())
    if category:
        query = query.filter(Classification.category == category.upper())

    total = query.count()
    rows = (
        query.order_by(Recommendation.confidence.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "gmail_message_id": m.gmail_message_id,
                "subject": m.subject,
                "sender_domain": m.sender_domain,
                "received_at": m.received_at.isoformat() if m.received_at else None,
                "action": r.action,
                "confidence": r.confidence,
                "risk": r.risk,
                "reasons": r.reasons,
                "category": str(c.category) if c else None,
                "is_starred": m.is_starred,
                "has_attachments": m.has_attachments,
            }
            for r, m, c in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/{rec_id}", summary="One recommendation with full explanation")
def get_recommendation(
    rec_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    base = _base_query(db, user)
    row = None if base is None else base.filter(Recommendation.id == rec_id).one_or_none()
    if row is None:
        raise NotFoundError("Recommendation not found.")
    r, m, c = row
    return {
        "id": str(r.id),
        "action": r.action,
        "confidence": r.confidence,
        "risk": r.risk,
        "reasons": r.reasons,
        "contributing_rule_ids": r.contributing_rule_ids,
        "status": r.status,
        "message": {
            "gmail_message_id": m.gmail_message_id,
            "subject": m.subject,
            "sender_name": m.sender_name,
            "sender_email": m.sender_email,
            "received_at": m.received_at.isoformat() if m.received_at else None,
            "has_attachments": m.has_attachments,
        },
        "classification": {
            "category": str(c.category) if c else None,
            "source": str(c.source) if c else None,
            "ai_reasoning": c.ai_reasoning if c else None,
        },
    }
