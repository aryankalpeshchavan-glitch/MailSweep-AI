"""End-to-end pipeline tests against a scripted fake Gmail client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.analysis.pipeline import run_mailbox_analysis
from app.gmail.models import GmailMessageMeta
from app.models import (
    AnalysisJob,
    AuditLog,
    Classification,
    CleanupRule,
    EmailGroup,
    EmailMessage,
    Mailbox,
    Recommendation,
    User,
)
from sqlalchemy.orm import Session

_NOW = datetime(2026, 8, 25, tzinfo=UTC)


class FakeGmailClient:
    """Scripted GmailClientProtocol implementation for pipeline tests."""

    def __init__(self, metas: list[GmailMessageMeta], fail_ids: set[str] | None = None):
        self.metas = {m.gmail_id: m for m in metas}
        self.fail_ids = fail_ids or set()
        self.trashed: list[str] = []

    def list_message_ids(self, *, page_size: int, max_total: int) -> list[str]:
        return [m.gmail_id for m in self.metas.values()][:max_total]

    def get_metadata(self, message_id: str) -> GmailMessageMeta:
        if message_id in self.fail_ids:
            raise RuntimeError("simulated permanent fetch failure")
        return self.metas[message_id]

    def trash_message(self, message_id: str) -> None:
        self.trashed.append(message_id)

    def close(self) -> None:
        pass


def _meta(gmail_id: str, **overrides) -> GmailMessageMeta:
    values = dict(
        gmail_id=gmail_id,
        thread_id=f"th-{gmail_id}",
        sender_email="news@bulk.example",
        sender_domain="bulk.example",
        subject="Weekly digest",
        received_at=_NOW - timedelta(days=6 * 365),
        label_ids=["CATEGORY_PROMOTIONS"],
        has_list_unsubscribe=True,
    )
    values.update(overrides)
    return GmailMessageMeta(**values)


@pytest.fixture()
def seeded(db_engine):
    db = Session(bind=db_engine)
    user = User(email="flow@example.com", display_name="Flow")
    db.add(user)
    db.flush()
    mailbox = Mailbox(user_id=user.id, google_email_address=user.email)
    db.add(mailbox)
    db.flush()
    job = AnalysisJob(user_id=user.id, mailbox_id=mailbox.id)
    db.add(job)
    db.commit()
    yield {"user": user, "mailbox": mailbox, "job": job, "engine": db_engine}
    db.close()


def _run(world, gmail) -> None:
    from tests.conftest import make_test_settings

    run_mailbox_analysis(
        Session(bind=world["engine"]),
        job_id=str(world["job"].id),
        gmail=gmail,
        settings=make_test_settings(),
    )


def _check(engine) -> Session:
    return Session(bind=engine)


def test_full_pipeline_produces_messages_groups_recommendations(seeded):
    gmail = FakeGmailClient([
        _meta("promo-1"),
        _meta("promo-2", subject="Mega deals inside"),
        _meta(
            "receipt-1", sender_email="orders@shop.example",
            sender_domain="shop.example", subject="Your receipt",
            label_ids=[], has_list_unsubscribe=False,
            received_at=_NOW - timedelta(days=400),
        ),
        _meta("starred-1", is_starred=True),
    ])
    _run(seeded, gmail)

    db = _check(seeded["engine"])
    job = db.get(AnalysisJob, seeded["job"].id)
    assert job.status == "COMPLETED"
    assert job.messages_total == 4 and job.messages_processed == 4
    assert job.completed_at is not None

    assert db.query(EmailMessage).count() == 4
    assert db.query(Classification).count() == 4
    assert db.query(EmailGroup).count() >= 3

    starred_rec = (
        db.query(Recommendation).join(EmailMessage)
        .filter(EmailMessage.gmail_message_id == "starred-1").one()
    )
    assert starred_rec.action == "KEEP"
    assert any(r["code"] == "starred" for r in starred_rec.reasons)

    trash_count = (
        db.query(Recommendation).filter_by(action="MOVE_TO_TRASH").count()
    )
    assert trash_count >= 2  # old promos with unsubscribe evidence

    events = [e.event_type for e in db.query(AuditLog).all()]
    assert "ANALYSIS_COMPLETED" in events
    assert "RECOMMENDATIONS_GENERATED" in events


def test_rerun_upserts_without_duplicates(seeded):
    gmail = FakeGmailClient([_meta("promo-1"), _meta("promo-2")])
    _run(seeded, gmail)
    _run(seeded, gmail)

    db = _check(seeded["engine"])
    assert db.query(EmailMessage).count() == 2
    assert db.query(Recommendation).count() == 2
    assert db.query(Classification).count() == 2
    assert db.get(AnalysisJob, seeded["job"].id).status == "COMPLETED"


def test_individual_fetch_failures_are_skipped(seeded):
    gmail = FakeGmailClient([_meta("promo-1"), _meta("bad-1")], fail_ids={"bad-1"})
    _run(seeded, gmail)

    db = _check(seeded["engine"])
    assert db.get(AnalysisJob, seeded["job"].id).status == "COMPLETED"
    assert db.query(EmailMessage).count() == 1


def test_hard_failure_marks_job_failed_and_audits(seeded):
    """Failure contract: FAILED state + reason + finished stamp + audit,
    while the exception still propagates to the runner for ops visibility."""
    class ExplodingClient(FakeGmailClient):
        def list_message_ids(self, **kwargs):
            raise RuntimeError("quota exhausted permanently")

    with pytest.raises(RuntimeError):
        _run(seeded, ExplodingClient([_meta("x")]))

    db = _check(seeded["engine"])
    job = db.get(AnalysisJob, seeded["job"].id)
    assert job.status == "FAILED"
    assert job.error_code == "RuntimeError"
    assert job.error_message  # reason recorded (truncated, secret-free)
    assert job.completed_at is not None  # finished state stamped
    assert "ANALYSIS_FAILED" in [e.event_type for e in db.query(AuditLog).all()]


def test_protection_rule_changes_recommendation(seeded):
    setup = Session(bind=seeded["engine"])
    setup.add(CleanupRule(
        user_id=seeded["user"].id, name="Protect bulk.example", kind="PROTECT",
        match_all=True,
        conditions=[{"field": "sender_domain", "op": "eq", "value": "bulk.example"}],
    ))
    setup.commit()

    _run(seeded, FakeGmailClient([_meta("promo-1")]))

    check = _check(seeded["engine"])
    rec = check.query(Recommendation).one()
    assert rec.action == "KEEP"
    assert any(r["code"] == "protection_rule" for r in rec.reasons)


def test_inline_dispatcher_runs_pipeline_blocking(seeded, monkeypatch):
    """The blocking inline path executes the real pipeline end-to-end."""
    from app.db.session import create_engine_and_sessionmaker
    from app.workers import tasks as task_module

    from tests.conftest import make_test_settings

    file_url = seeded["engine"].url.render_as_string(hide_password=False)
    settings = make_test_settings(DATABASE_URL=file_url)

    engine, factory = create_engine_and_sessionmaker(settings.normalized_database_url)
    monkeypatch.setattr(task_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        task_module, "create_engine_and_sessionmaker", lambda url: (engine, factory)
    )
    monkeypatch.setattr(
        task_module, "get_valid_access_token", lambda *a, **k: "fake-token"
    )
    fake = FakeGmailClient([_meta("promo-inline")])
    monkeypatch.setattr(
        task_module, "GoogleGmailClient", lambda token, s: fake
    )

    from app.workers.dispatcher import run_inline_blocking

    run_inline_blocking(str(seeded["job"].id))
    engine.dispose()

    check = _check(seeded["engine"])
    assert check.get(AnalysisJob, seeded["job"].id).status == "COMPLETED"
    rec = (
        check.query(Recommendation).join(EmailMessage)
        .filter(EmailMessage.gmail_message_id == "promo-inline").one()
    )
    assert rec.action == "MOVE_TO_TRASH"
