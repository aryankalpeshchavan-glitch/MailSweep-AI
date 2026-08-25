"""Group browsing endpoints (paginated, owner-scoped)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models import EmailGroup, EmailMessage, Mailbox, Recommendation, User

router = APIRouter(prefix="/api/groups", tags=["mailbox-browse"])


def _mailbox_id(db: Session, user: User) -> uuid.UUID | None:
    return db.query(Mailbox.id).filter_by(user_id=user.id).scalar()


@router.get("", summary="Browse email groups")
def list_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    mailbox_id = _mailbox_id(db, user)
    if mailbox_id is None:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}

    query = db.query(EmailGroup).filter_by(mailbox_id=mailbox_id)
    if category:
        query = query.filter(EmailGroup.primary_category == category.upper())
    total = query.count()
    groups = (
        query.order_by(EmailGroup.message_count.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": str(g.id),
                "display_name": g.display_name,
                "primary_sender_domain": g.primary_sender_domain,
                "category": str(g.primary_category) if g.primary_category else None,
                "message_count": g.message_count,
                "first_message_at": (
                    g.first_message_at.isoformat() if g.first_message_at else None
                ),
                "last_message_at": (
                    g.last_message_at.isoformat() if g.last_message_at else None
                ),
                "sample_subjects": g.sample_subjects,
            }
            for g in groups
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/{group_id}", summary="One group with its messages")
def get_group(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    group = (
        db.query(EmailGroup)
        .join(Mailbox, EmailGroup.mailbox_id == Mailbox.id)
        .filter(EmailGroup.id == group_id, Mailbox.user_id == user.id)
        .one_or_none()
    )
    if group is None:
        raise NotFoundError("Group not found.")

    messages = (
        db.query(EmailMessage, Recommendation)
        .outerjoin(Recommendation, Recommendation.message_id == EmailMessage.id)
        .filter(EmailMessage.group_id == group.id)
        .order_by(EmailMessage.received_at.desc())
        .limit(200)
        .all()
    )
    return {
        "id": str(group.id),
        "display_name": group.display_name,
        "primary_sender_domain": group.primary_sender_domain,
        "category": str(group.primary_category) if group.primary_category else None,
        "message_count": group.message_count,
        "messages": [
            {
                "id": str(m.id),
                "subject": m.subject,
                "sender_email": m.sender_email,
                "received_at": m.received_at.isoformat() if m.received_at else None,
                "is_starred": m.is_starred,
                "recommendation_action": r.action if r else None,
                "recommendation_confidence": r.confidence if r else None,
                "risk": r.risk if r else None,
            }
            for m, r in messages
        ],
    }
