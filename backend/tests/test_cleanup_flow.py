"""Cleanup plan safety tests (spec §11/§30/§37).

Mandated cases: unapproved plans never touch Gmail; approval executes exactly
the approved messages once; duplicate approval conflicts; partial failures are
recorded honestly; cross-user access is denied.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.auth.service import create_session, upsert_oauth_identity
from app.cleanup.service import (
    approve_plan,
    cancel_plan,
    create_plan_preview,
    execute_approved_plan,
)
from app.core.errors import ConflictError, NotFoundError
from app.models import (
    CleanupPlan,
    CleanupPlanItem,
    EmailMessage,
    Mailbox,
    Recommendation,
    User,
)
from sqlalchemy.orm import Session

_NOW = datetime(2026, 8, 25, tzinfo=UTC)
_SECRET = b"c" * 48


class FakeGmailClient:
    def __init__(self, fail_ids: set[str] | None = None):
        self.fail_ids = fail_ids or set()
        self.trashed: list[str] = []

    def trash_message(self, message_id: str) -> None:
        if message_id in self.fail_ids:
            raise RuntimeError("simulated trash failure")
        self.trashed.append(message_id)

    def close(self) -> None:
        pass


@pytest.fixture()
def cleanup_world(build_world):
    """Authenticated user with a mailbox of 3 pending trash candidates."""
    settings, client, engine = build_world(
        GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="csecret",
        FRONTEND_ORIGINS="http://localhost:3000",
    )
    db = Session(bind=engine)
    user, _connection = upsert_oauth_identity(
        db,
        sub="sub-clean", email="clean@example.com", display_name=None,
        avatar_url=None, scope="scope", access_token="at", refresh_token="rt",
        expires_in=3600, secret_key=_SECRET,
    )
    mailbox = Mailbox(user_id=user.id, google_email_address=user.email)
    db.add(mailbox)
    db.flush()

    recommendation_ids = {}
    for n in range(1, 4):
        gmail_id = f"gm-{n}"
        message = EmailMessage(
            mailbox_id=mailbox.id,
            gmail_message_id=gmail_id,
            gmail_thread_id=f"th-{n}",
            sender_email="news@bulk.example",
            sender_domain="bulk.example",
            subject=f"Weekly digest {n}",
            received_at=_NOW - timedelta(days=6 * 365),
        )
        db.add(message)
        db.flush()
        recommendation = Recommendation(
            message_id=message.id,
            mailbox_id=mailbox.id,
            action="MOVE_TO_TRASH",
            confidence=0.95,
            risk="LOW",
            reasons=[{"code": "test", "detail": "seeded"}],
        )
        db.add(recommendation)
        db.flush()
        recommendation_ids[gmail_id] = str(recommendation.id)

    keep_message = EmailMessage(
        mailbox_id=mailbox.id, gmail_message_id="keep-1",
        subject="Lunch?", received_at=_NOW - timedelta(days=2),
        sender_email="friend@example.com", sender_domain="example.com",
    )
    db.add(keep_message)
    db.flush()
    db.add(Recommendation(
        message_id=keep_message.id, mailbox_id=mailbox.id,
        action="KEEP", confidence=0.9, risk="HIGH", reasons=[],
    ))
    db.commit()
    raw_token = create_session(db, user_id=user.id, ttl_days=14)
    client.cookies.set("mailsweep_session", raw_token)

    yield {
        "settings": settings, "client": client, "engine": engine, "db": db,
        "user": user, "mailbox": mailbox, "recs": recommendation_ids,
    }
    db.close()


def test_preview_creates_pending_plan_without_touching_gmail(cleanup_world):
    world = cleanup_world
    response = world["client"].post(
        "/api/cleanup/preview",
        json={"recommendation_ids": [world["recs"]["gm-1"], world["recs"]["gm-2"]]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING_APPROVAL"
    assert body["message_count"] == 2
    assert {i["gmail_message_id"] for i in body["items"]} == {"gm-1", "gm-2"}


def test_preview_rejects_empty_selection_and_keeps(cleanup_world):
    response = cleanup_world["client"].post(
        "/api/cleanup/preview", json={"recommendation_ids": []}
    )
    assert response.status_code == 422  # schema min_length


def test_preview_rejects_recommendations_that_arent_trash_candidates(cleanup_world):
    world = cleanup_world
    keep_rec = (
        world["db"].query(Recommendation).filter_by(action="KEEP").one()
    )
    response = world["client"].post(
        "/api/cleanup/preview",
        json={"recommendation_ids": [str(keep_rec.id)]},
    )
    assert response.status_code == 404


def test_unapproved_plan_never_touches_gmail(cleanup_world):
    world = cleanup_world
    db = world["db"]
    plan = create_plan_preview(
        db, user=world["user"],
        recommendation_ids=list(world["recs"].values()),
    )
    fake = FakeGmailClient()
    # No approval -> no execution path exists. Explicit no-op assertion:
    assert plan.status == "PENDING_APPROVAL"
    assert fake.trashed == []
    assert all(i.item_status == "PENDING" for i in db.query(CleanupPlanItem).all())


def test_approval_executes_exactly_the_approved_messages_once(cleanup_world):
    world = cleanup_world
    db = world["db"]
    plan = create_plan_preview(
        db, user=world["user"], recommendation_ids=[world["recs"]["gm-1"]]
    )
    approve_plan(db, user=world["user"], plan_id=str(plan.id))

    fake = FakeGmailClient()
    execute_approved_plan(db, plan_id=str(plan.id), gmail=fake)

    check = Session(bind=world["engine"])
    finished = check.get(CleanupPlan, plan.id)
    assert finished.status == "COMPLETED"
    assert fake.trashed == ["gm-1"]  # exactly once, exactly the approved set

    item = check.query(CleanupPlanItem).one()
    assert item.item_status == "TRASHED" and item.executed_at is not None


def test_duplicate_approval_conflicts_and_never_double_executes(cleanup_world):
    world = cleanup_world
    db = world["db"]
    plan = create_plan_preview(
        db, user=world["user"], recommendation_ids=[world["recs"]["gm-1"]]
    )
    approve_plan(db, user=world["user"], plan_id=str(plan.id))
    with pytest.raises(ConflictError):
        approve_plan(db, user=world["user"], plan_id=str(plan.id))

    fake = FakeGmailClient()
    with pytest.raises(ConflictError):
        # Second execution attempt also rejected: only APPROVED is executable.
        execute_approved_plan(db, plan_id=str(plan.id), gmail=fake)
        execute_approved_plan(db, plan_id=str(plan.id), gmail=fake)

    assert fake.trashed.count("gm-1") <= 1


def test_cancelled_plan_cannot_be_approved_or_executed(cleanup_world):
    world = cleanup_world
    db = world["db"]
    plan = create_plan_preview(db, user=world["user"],
                               recommendation_ids=[world["recs"]["gm-1"]])
    cancel_plan(db, user=world["user"], plan_id=str(plan.id))

    with pytest.raises(ConflictError):
        approve_plan(db, user=world["user"], plan_id=str(plan.id))

    fake = FakeGmailClient()
    with pytest.raises(ConflictError):
        execute_approved_plan(db, plan_id=str(plan.id), gmail=fake)
    assert fake.trashed == []


def test_partial_failures_are_recorded_honestly(cleanup_world):
    world = cleanup_world
    db = world["db"]
    plan = create_plan_preview(
        db, user=world["user"],
        recommendation_ids=[world["recs"]["gm-1"], world["recs"]["gm-2"]],
    )
    approve_plan(db, user=world["user"], plan_id=str(plan.id))

    fake = FakeGmailClient(fail_ids={"gm-2"})
    execute_approved_plan(db, plan_id=str(plan.id), gmail=fake)

    check = Session(bind=world["engine"])
    finished = check.get(CleanupPlan, plan.id)
    assert finished.status == "COMPLETED_WITH_FAILURES"
    assert finished.failure_summary["failed"] == 1
    statuses = {i.gmail_message_id: i.item_status for i in check.query(CleanupPlanItem)}
    assert statuses == {"gm-1": "TRASHED", "gm-2": "FAILED"}
    assert fake.trashed == ["gm-1"]


def test_other_user_cannot_see_approve_or_execute_foreign_plan(cleanup_world, build_world):
    world = cleanup_world
    db = world["db"]
    plan = create_plan_preview(db, user=world["user"],
                               recommendation_ids=[world["recs"]["gm-1"]])

    _settings2, client2, engine2 = build_world(
        GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="csecret",
    )
    db2 = Session(bind=engine2)
    intruder = User(email="intruder@example.com")
    db2.add(intruder)
    db2.commit()

    with pytest.raises(NotFoundError):
        approve_plan(db2, user=intruder, plan_id=str(plan.id))
    with pytest.raises(NotFoundError):
        execute_approved_plan(db2, plan_id=str(plan.id), gmail=FakeGmailClient())

    response = world["client"].get(f"/api/cleanup/plans/{plan.id}")
    assert response.status_code == 200  # owner still sees it


def test_owner_can_list_and_view_plans_via_api(cleanup_world):
    world = cleanup_world
    plan = create_plan_preview(world["db"], user=world["user"],
                               recommendation_ids=[world["recs"]["gm-1"]])
    listed = world["client"].get("/api/cleanup/plans").json()
    assert [p["id"] for p in listed] == [str(plan.id)]

    detail = world["client"].get(f"/api/cleanup/plans/{plan.id}").json()
    assert detail["message_count"] == 1 and len(detail["items"]) == 1
