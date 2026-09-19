"""Analysis workflow regression tests.

Covers the end-to-end contract the dashboard depends on:

* first-analysis lazy Mailbox creation + active-job lookup,
* 409 conflict on a second start while a job is active,
* GET /api/analysis/active (returns the latest active job, never another
  user's job, null when none exists, ignores terminal jobs),
* stale QUEUED jobs are recovered safely so the user can retry,
* inline dispatch actually invokes ``execute_analysis_job``,
* a pre-pipeline execution failure leaves the job FAILED (never silently
  stuck QUEUED), with a safe error recorded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.auth.service import create_session, upsert_oauth_identity
from app.models import AnalysisJob, Mailbox, User
from app.models.enums import AnalysisJobStatus
from sqlalchemy.orm import Session

from tests.conftest import make_test_settings

_SECRET = b"w" * 48


def _make_connected_world(build_world, sub: str, email: str):
    """Seed an authenticated, Google-connected user with a Mailbox."""
    settings, client, engine = build_world(
        GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="csecret",
        FRONTEND_ORIGINS="http://localhost:3000",
    )
    db = Session(bind=engine, expire_on_commit=False)
    user, _ = upsert_oauth_identity(
        db,
        sub=sub, email=email, display_name=None,
        avatar_url=None, scope="scope", access_token="at", refresh_token="rt",
        expires_in=3600, secret_key=_SECRET,
    )
    mailbox = Mailbox(user_id=user.id, google_email_address=user.email)
    db.add(mailbox)
    db.flush()
    db.commit()
    client.cookies.set("mailsweep_session", create_session(db, user_id=user.id, ttl_days=14))
    db.close()
    return settings, client, engine, user, mailbox


@pytest.fixture()
def connected_world(build_world):
    settings, client, engine, user, mailbox = _make_connected_world(
        build_world, sub="sub-workflow", email="wf@example.com"
    )
    yield {
        "settings": settings,
        "client": client,
        "engine": engine,
        "user": user,
        "mailbox": mailbox,
    }


def test_first_analysis_creates_mailbox_and_active_job(build_world):
    """Connected user + NO mailbox + POST /start -> 202, Mailbox + job created."""
    _settings, client, engine, user, _mailbox = _make_connected_world(
        build_world, sub="sub-first", email="first@example.com"
    )

    response = client.post("/api/analysis/start")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["dispatched_to"] == "inline"

    db = Session(bind=engine)
    try:
        mailbox = db.query(Mailbox).filter_by(user_id=user.id).one()
        job = db.query(AnalysisJob).filter_by(user_id=user.id).one()
        assert str(job.mailbox_id) == str(mailbox.id)
        assert body["job_id"] == str(job.id)
    finally:
        db.close()

    active = client.get("/api/analysis/active").json()
    assert active["active"]["job_id"] == body["job_id"]
    assert active["active"]["status"] == "QUEUED"


def test_second_start_conflicts_while_job_active(connected_world):
    world = connected_world
    first = world["client"].post("/api/analysis/start")
    assert first.status_code == 202

    second = world["client"].post("/api/analysis/start")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"

    # The original active job is untouched and still the active one.
    active = world["client"].get("/api/analysis/active").json()
    assert active["active"]["job_id"] == first.json()["job_id"]


def test_active_returns_none_without_job(connected_world):
    body = connected_world["client"].get("/api/analysis/active").json()
    assert body == {"active": None}


def test_active_ignores_completed_and_failed_jobs(connected_world):
    world = connected_world
    start = world["client"].post("/api/analysis/start")
    assert start.status_code == 202
    job_id = uuid.UUID(start.json()["job_id"])

    db = Session(bind=world["engine"])
    try:
        db.query(AnalysisJob).filter_by(id=job_id).update(
            {
                "status": "COMPLETED",
                "started_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            }
        )
        db.commit()
    finally:
        db.close()
    assert world["client"].get("/api/analysis/active").json() == {"active": None}

    # New active job, then failed -> also invisible to /active.
    second = world["client"].post("/api/analysis/start")
    assert second.status_code == 202
    db = Session(bind=world["engine"])
    try:
        db.query(AnalysisJob).filter_by(id=uuid.UUID(second.json()["job_id"])).update(
            {"status": "FAILED", "completed_at": datetime.now(UTC)}
        )
        db.commit()
    finally:
        db.close()
    assert world["client"].get("/api/analysis/active").json() == {"active": None}
def test_active_never_exposes_another_users_job(connected_world):
    world = connected_world
    own = world["client"].post("/api/analysis/start")
    assert own.status_code == 202

    # A second user with their own active job must stay invisible.
    db = Session(bind=world["engine"], expire_on_commit=False)
    other, _ = upsert_oauth_identity(
        db,
        sub="sub-other", email="other@example.com", display_name=None,
        avatar_url=None, scope="scope", access_token="at", refresh_token="rt",
        expires_in=3600, secret_key=_SECRET,
    )
    other_mailbox = Mailbox(user_id=other.id, google_email_address=other.email)
    db.add(other_mailbox)
    db.flush()
    db.add(AnalysisJob(user_id=other.id, mailbox_id=other_mailbox.id))
    db.commit()
    db.close()

    active = world["client"].get("/api/analysis/active").json()
    assert active["active"]["job_id"] == own.json()["job_id"]

    # And the other user's job is not reachable via the scoped poll route.
    db = Session(bind=world["engine"])
    try:
        other_job_id = db.query(AnalysisJob).filter_by(user_id=other.id).one().id
    finally:
        db.close()
    poll = world["client"].get(f"/api/analysis/jobs/{other_job_id}")
    assert poll.status_code == 404


def test_active_requires_authentication(build_world):
    _settings, client, _engine, _user, _mailbox = _make_connected_world(
        build_world, sub="sub-anon", email="anon@example.com"
    )
    # Drop the session cookie so the request is anonymous.
    client.cookies.clear()
    response = client.get("/api/analysis/active")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_inline_dispatcher_invokes_execute_analysis_job(monkeypatch):
    """Inline dispatch must actually run the shared task, not just queue it."""
    from app.workers import dispatcher

    captured: dict[str, str] = {}

    def fake_execute(job_id: str) -> None:
        captured["job_id"] = job_id

    monkeypatch.setattr(dispatcher, "execute_analysis_job", fake_execute)

    started: list = []

    class FakeThread:
        def __init__(self, target, args=(), name=None, daemon=None):
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon

        def start(self) -> None:
            started.append(self)

    monkeypatch.setattr(dispatcher, "threading", SimpleNamespace(Thread=FakeThread))

    settings = make_test_settings(
        REDIS_URL="redis://redis.example.com:6379/0", JOB_DISPATCH_MODE="inline"
    )
    marker = dispatcher.dispatch_analysis("job-inline", settings=settings)
    assert marker == "inline"
    assert len(started) == 1
    # Simulate the background thread running: it must reach execute_analysis_job.
    started[0].target(*started[0].args)
    assert captured == {"job_id": "job-inline"}
def test_pre_pipeline_failure_marks_job_failed(build_world, monkeypatch):
    """A failure before the pipeline (no OAuth connection) must FAIL the job."""
    _settings, _client, engine, user, mailbox = _make_connected_world(
        build_world, sub="sub-noconn", email="noconn@example.com"
    )
    db = Session(bind=engine)
    # Detach the user from any OAuthConnection so token retrieval raises.
    user = db.query(User).filter_by(id=user.id).one()
    db.delete(user.oauth_connection)

    job = AnalysisJob(user_id=user.id, mailbox_id=mailbox.id)
    db.add(job)
    db.commit()
    job_id = str(job.id)
    db.close()

    from app.workers import tasks as task_module

    file_url = engine.url.render_as_string(hide_password=False)
    run_settings = make_test_settings(DATABASE_URL=file_url)
    monkeypatch.setattr(task_module, "get_settings", lambda: run_settings)

    with pytest.raises(Exception) as excinfo:
        task_module.execute_analysis_job(job_id)
    assert excinfo.type.__name__ == "ExternalServiceError"

    db = Session(bind=engine)
    try:
        failed = db.get(AnalysisJob, uuid.UUID(job_id))
        assert failed.status == "FAILED"
        assert failed.error_code == "ExternalServiceError"
        assert failed.error_message  # safe, human-readable reason
        assert failed.started_at is None  # never started
        assert failed.completed_at is not None  # terminal stamp
    finally:
        db.close()


def test_running_job_is_never_marked_stale(connected_world):
    """Long-running jobs with started_at set must not be auto-failed."""
    world = connected_world
    db = Session(bind=world["engine"])
    job = AnalysisJob(user_id=world["user"].id, mailbox_id=world["mailbox"].id)
    job.status = AnalysisJobStatus.RUNNING.value
    job.started_at = datetime.now(UTC) - timedelta(hours=2)  # older than threshold
    db.add(job)
    db.commit()
    job_id = str(job.id)
    db.close()

    active = world["client"].get("/api/analysis/active").json()
    assert active["active"]["job_id"] == job_id
    assert active["active"]["status"] == "RUNNING"

    db = Session(bind=world["engine"])
    try:
        fresh = db.get(AnalysisJob, uuid.UUID(job_id))
        assert fresh.status == "RUNNING"
        assert fresh.error_code is None
    finally:
        db.close()
def test_stale_queued_job_is_recovered_and_user_can_retry(connected_world):
    """A QUEUED-never-started job past the timeout is failed automatically."""
    world = connected_world
    db = Session(bind=world["engine"])
    stale = AnalysisJob(user_id=world["user"].id, mailbox_id=world["mailbox"].id)
    db.add(stale)
    db.flush()
    stale.created_at = datetime.now(UTC) - timedelta(
        seconds=world["settings"].STALE_QUEUED_JOB_TIMEOUT_SECONDS + 60
    )
    db.commit()
    stale_id = str(stale.id)
    db.close()

    # GET /active recovers the stale job -> no active job to resume.
    assert world["client"].get("/api/analysis/active").json() == {"active": None}

    db = Session(bind=world["engine"])
    try:
        recovered = db.get(AnalysisJob, uuid.UUID(stale_id))
        assert recovered.status == "FAILED"
        assert recovered.error_code == "STALE_QUEUED_JOB"
        assert recovered.completed_at is not None
    finally:
        db.close()

    # The user can start a fresh analysis without manual DB edits, reusing the mailbox.
    response = world["client"].post("/api/analysis/start")
    assert response.status_code == 202
    db = Session(bind=world["engine"])
    try:
        assert db.query(Mailbox).filter_by(user_id=world["user"].id).count() == 1
        jobs = db.query(AnalysisJob).filter_by(user_id=world["user"].id).all()
        assert len(jobs) == 2
        assert all(str(j.mailbox_id) == str(world["mailbox"].id) for j in jobs)
    finally:
        db.close()
