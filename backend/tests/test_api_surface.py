"""API surface tests: analysis start/poll, summary, groups, recommendations,
rules CRUD, audit, and rate limiting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.auth.service import create_session, record_event, upsert_oauth_identity
from app.models import (
    EmailMessage,
    Mailbox,
    Recommendation,
)
from app.models.enums import AuditEvent
from sqlalchemy.orm import Session

_SECRET = b"a" * 48


@pytest.fixture()
def api_world(build_world):
    """Authenticated user with an analyzed mailbox (messages + recommendations)."""
    settings, client, engine = build_world(
        GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="csecret",
        FRONTEND_ORIGINS="http://localhost:3000",
    )
    db = Session(bind=engine)
    user, _ = upsert_oauth_identity(
        db,
        sub="sub-dash", email="dash@example.com", display_name=None,
        avatar_url=None, scope="scope", access_token="at", refresh_token="rt",
        expires_in=3600, secret_key=_SECRET,
    )
    mailbox = Mailbox(user_id=user.id, google_email_address=user.email,
                      total_messages_cached=3,
                      last_analysis_at=datetime.now(UTC))
    db.add(mailbox)
    db.flush()

    now = datetime.now(UTC)
    group_id = None
    for n in range(3):
        message = EmailMessage(
            mailbox_id=mailbox.id, gmail_message_id=f"gm-{n}",
            sender_email="news@bulk.example", sender_domain="bulk.example",
            subject=f"Weekly digest {n}",
            received_at=now - timedelta(days=6 * 365),
            group_id=group_id,
        )
        db.add(message)
        db.flush()
        if group_id is None:
            from app.analysis.grouping import build_group_key
            from app.models import EmailGroup

            new_group = EmailGroup(
                mailbox_id=mailbox.id,
                group_key=build_group_key("bulk.example", "PROMOTIONAL", "Week"),
                display_name="Bulk",
                primary_sender_domain="bulk.example",
                primary_category="PROMOTIONAL",
                message_count=3,
            )
            db.add(new_group)
            db.flush()
            group_id = new_group.id
            message.group_id = group_id
        db.add(Recommendation(
            message_id=message.id, mailbox_id=mailbox.id,
            action="MOVE_TO_TRASH", confidence=0.95, risk="LOW",
            reasons=[{"code": "seed", "detail": "x"}],
        ))
    db.commit()

    client.cookies.set("mailsweep_session", create_session(db, user_id=user.id, ttl_days=14))
    record_event(db, event_type=AuditEvent.ACCOUNT_CONNECTED, user_id=user.id)

    yield {
        "settings": settings, "client": client,
        "engine": engine, "user": user, "mailbox": mailbox,
    }
    db.close()


def test_summary_dashboard_cards(api_world):
    body = api_world["client"].get("/api/mailbox/summary").json()
    assert body["analyzed"] is True
    assert body["recommendations"]["move_to_trash"] == 3
    assert body["top_groups"][0]["message_count"] == 3


def test_anonymous_access_is_rejected(api_world):
    api_world["client"].cookies.clear()
    assert api_world["client"].get("/api/mailbox/summary").status_code == 401
    assert api_world["client"].get("/api/groups").status_code == 401


def test_recommendations_list_and_detail(api_world):
    listed = api_world["client"].get("/api/recommendations").json()
    assert listed["total"] == 3
    rec_id = listed["items"][0]["id"]

    detail = api_world["client"].get(f"/api/recommendations/{rec_id}").json()
    assert detail["action"] == "MOVE_TO_TRASH"
    assert detail["reasons"] == [{"code": "seed", "detail": "x"}]


def test_recommendation_filters(api_world):
    body = api_world["client"].get(
        "/api/recommendations", params={"action": "KEEP"}
    ).json()
    assert body["total"] == 0


def test_group_detail_shows_messages_with_recommendation(api_world):
    groups = api_world["client"].get("/api/groups").json()
    gid = groups["items"][0]["id"]
    detail = api_world["client"].get(f"/api/groups/{gid}").json()
    assert detail["message_count"] == 3
    assert all(m["recommendation_action"] == "MOVE_TO_TRASH" for m in detail["messages"])


def test_rule_lifecycle_via_api(api_world):
    client = api_world["client"]
    created = client.post(
        "/api/rules",
        json={
            "name": "Protect university",
            "kind": "PROTECT",
            "match_all": True,
            "conditions": [
                {"field": "sender_domain", "op": "ends_with", "value": "university.edu"}
            ],
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    updated = client.put(
        f"/api/rules/{rule_id}",
        json={"enabled": False, "priority": 10},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    listed = client.get("/api/rules").json()
    assert listed[0]["name"] == "Protect university"

    assert client.delete(f"/api/rules/{rule_id}").status_code == 204
    assert client.get("/api/rules").json() == []


def test_rule_rejects_invalid_condition(api_world):
    response = api_world["client"].post(
        "/api/rules",
        json={
            "name": "Bad",
            "kind": "CLEANUP",
            "conditions": [{"field": "email_body", "op": "contains", "value": "x"}],
        },
    )
    assert response.status_code == 422


def test_audit_endpoint_lists_events(api_world):
    body = api_world["client"].get("/api/audit").json()
    assert body["total"] >= 1
    assert any(e["event_type"] == "ACCOUNT_CONNECTED" for e in body["items"])
    assert body["items"][0]["created_at"]  # isoformat
