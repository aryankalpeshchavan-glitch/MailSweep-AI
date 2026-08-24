"""Database schema behavior: constraints, cascades, relationship integrity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models import (
    AuditLog,
    CleanupPlan,
    CleanupPlanItem,
    EmailMessage,
    Mailbox,
    OAuthConnection,
    User,
)
from app.models.enums import OAuthStatus
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture()
def db(db_engine) -> Session:
    return Session(bind=db_engine)


def _make_user_graph(db: Session, *, email: str = "student@example.com") -> User:
    user = User(email=email, display_name="Student")
    db.add(user)
    db.flush()

    db.add(
        OAuthConnection(
            user_id=user.id,
            google_sub=f"sub-{email}",
            google_email=email,
            status=OAuthStatus.ACTIVE,
            connected_at=datetime.now(UTC),
        )
    )
    mailbox = Mailbox(user_id=user.id, google_email_address=email)
    db.add(mailbox)
    db.flush()

    now = datetime.now(UTC)
    db.add_all(
        [
            EmailMessage(
                mailbox_id=mailbox.id,
                gmail_message_id=f"gm-{n}",
                gmail_thread_id=f"th-{n}",
                sender_email="deals@shop.example",
                sender_domain="shop.example",
                subject=f"Huge sale {n}",
                received_at=now - timedelta(days=n),
            )
            for n in range(3)
        ]
    )
    db.commit()
    return user


def test_full_user_graph_roundtrip(db: Session):
    user = _make_user_graph(db)
    db.refresh(user)

    assert user.oauth_connection is not None
    assert user.oauth_connection.google_sub == "sub-student@example.com"
    assert len(user.sessions) == 0

    mailbox = user.oauth_connection and db.query(Mailbox).filter_by(user_id=user.id).one()
    assert mailbox is not None
    assert mailbox.total_messages_cached == 0  # updated by ingestion later
    assert db.query(EmailMessage).filter_by(mailbox_id=mailbox.id).count() == 3


def test_duplicate_gmail_message_per_mailbox_is_rejected(db: Session):
    user = _make_user_graph(db)
    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one()

    db.add(
        EmailMessage(
            mailbox_id=mailbox.id,
            gmail_message_id="gm-0",  # duplicate within this mailbox
            received_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_same_gmail_id_in_different_mailboxes_is_allowed(db: Session):
    first = _make_user_graph(db)
    other = _make_user_graph(db, email="other@example.com")

    m1 = db.query(Mailbox).filter_by(user_id=first.id).one()
    m2 = db.query(Mailbox).filter_by(user_id=other.id).one()
    # Same Gmail message cannot exist in two mailboxes in reality; the
    # constraint is scoped per-mailbox, so both inserts succeed here.
    assert m1 and m2 and m1.id != m2.id


def test_deleting_mailbox_cascades_to_messages(db: Session):
    user = _make_user_graph(db)
    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one()
    mailbox_id = mailbox.id

    db.delete(mailbox)
    db.commit()

    assert db.query(EmailMessage).filter_by(mailbox_id=mailbox_id).count() == 0


def test_deleting_user_keeps_audit_rows_but_nulls_reference(db: Session):
    user = _make_user_graph(db)
    audit = AuditLog(user_id=user.id, event_type="ANALYSIS_STARTED", detail={"x": 1})
    db.add(audit)
    db.commit()
    audit_id = audit.id

    db.delete(user)
    db.commit()

    survivor = db.get(AuditLog, audit_id)
    assert survivor is not None
    assert survivor.user_id is None
    assert survivor.event_type == "ANALYSIS_STARTED"


def test_cleanup_plan_items_snapshot_and_unique_constraint(db: Session):
    user = _make_user_graph(db)
    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one()
    messages = (
        db.query(EmailMessage)
        .filter_by(mailbox_id=mailbox.id)
        .order_by(EmailMessage.gmail_message_id)
        .all()
    )

    plan = CleanupPlan(user_id=user.id, mailbox_id=mailbox.id, status="PENDING_APPROVAL")
    db.add(plan)
    db.flush()
    db.add_all(
        [
            CleanupPlanItem(
                plan_id=plan.id,
                message_id=m.id,
                gmail_message_id=m.gmail_message_id,
                subject_snapshot=m.subject,
                sender_snapshot=m.sender_email,
            )
            for m in messages
        ]
    )
    db.commit()
    assert plan.message_count == 0  # set explicitly by the service layer
    assert db.query(CleanupPlanItem).filter_by(plan_id=plan.id).count() == 3

    duplicate = CleanupPlanItem(
        plan_id=plan.id,
        message_id=messages[0].id,  # already in plan
        gmail_message_id=messages[0].gmail_message_id,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
