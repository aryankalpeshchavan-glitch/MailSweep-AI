"""Dashboard summary endpoint (cards for the future frontend)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import EmailGroup, EmailMessage, Mailbox, OAuthConnection, Recommendation, User

router = APIRouter(prefix="/api/mailbox", tags=["mailbox"])


@router.get(
    "/summary",
    summary="Dashboard cards: connection state, cached volume, recommendation breakdown",
)
def mailbox_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    connection = db.query(OAuthConnection).filter_by(user_id=user.id).one_or_none()
    gmail_connected = bool(connection and str(connection.status) == "ACTIVE")

    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one_or_none()
    if mailbox is None:
        return {
            "gmail_connection": {
                "connected": gmail_connected,
                "email": connection.google_email if connection else None,
            },
            "analyzed": False,
        }

    action_counts = dict(
        db.query(Recommendation.action, func.count())
        .join(EmailMessage, EmailMessage.id == Recommendation.message_id)
        .filter(Recommendation.mailbox_id == mailbox.id, Recommendation.status == "pending")
        .group_by(Recommendation.action)
        .all()
    )
    risk_counts = dict(
        db.query(Recommendation.risk, func.count())
        .filter(Recommendation.mailbox_id == mailbox.id, Recommendation.status == "pending",
                Recommendation.action == "MOVE_TO_TRASH")
        .group_by(Recommendation.risk)
        .all()
    )
    top_groups = (
        db.query(EmailGroup)
        .filter_by(mailbox_id=mailbox.id)
        .order_by(EmailGroup.message_count.desc())
        .limit(5)
        .all()
    )

    return {
        "gmail_connection": {
            "connected": gmail_connected,
            "email": connection.google_email if connection else None,
        },
        "analyzed": True,
        "mailbox": {
            "email_address": mailbox.google_email_address,
            "total_messages_cached": mailbox.total_messages_cached,
            "last_analysis_at": (
                mailbox.last_analysis_at.isoformat() if mailbox.last_analysis_at else None
            ),
        },
        "recommendations": {
            "move_to_trash": action_counts.get("MOVE_TO_TRASH", 0),
            "review": action_counts.get("REVIEW", 0),
            "keep": action_counts.get("KEEP", 0),
            "trash_by_risk": {
                "low": risk_counts.get("LOW", 0),
                "medium": risk_counts.get("MEDIUM", 0),
                "high": risk_counts.get("HIGH", 0),
            },
        },
        "top_groups": [
            {
                "id": str(g.id),
                "display_name": g.display_name,
                "message_count": g.message_count,
                "category": str(g.primary_category) if g.primary_category else None,
            }
            for g in top_groups
        ],
    }
