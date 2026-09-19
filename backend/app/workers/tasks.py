"""Task bodies shared by Celery and the inline dispatcher."""

from __future__ import annotations

import logging
import uuid

from app.analysis.pipeline import run_mailbox_analysis
from app.auth.tokens import get_valid_access_token
from app.cleanup.service import execute_approved_plan
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import create_engine_and_sessionmaker
from app.gmail.client import GoogleGmailClient
from app.models import AnalysisJob, User
from app.models.enums import AnalysisJobStatus

logger = logging.getLogger(__name__)


def execute_analysis_job(job_id: str) -> None:
    """Own everything needed for one analysis run, then clean up.

    Workers are separate processes: they construct their own engine/session,
    refresh the access token if stale, bind a Gmail client, and hand both to
    the pipeline. Any failure - even before the pipeline begins (engine setup,
    token refresh, client construction) - is recorded on the job as FAILED with
    a safe error, then re-raised so the caller (inline thread or Celery) still
    observes the task failure.
    """
    settings = get_settings()
    engine, session_factory = create_engine_and_sessionmaker(
        settings.normalized_database_url
    )
    db = session_factory()
    job_pk: uuid.UUID | None = None
    try:
        job_pk = uuid.UUID(str(job_id))
        job = db.get(AnalysisJob, job_pk)
        if job is None:
            logger.error(
                "dispatched job missing", extra={"event": "job_missing", "job_id": job_id}
            )
            return
        user = db.get(User, job.user_id)
        access_token = get_valid_access_token(
            db, user=user, secret_key=settings.effective_secret_key(), settings=settings
        )
        gmail = GoogleGmailClient(access_token, settings)
        try:
            from app.ai.service import build_classifier

            run_mailbox_analysis(
                db, job_id=job_pk, gmail=gmail, settings=settings,
                ai_classifier=build_classifier(settings),
            )
        finally:
            gmail.close()
    except Exception as exc:  # noqa: BLE001 - converted into job failure state
        _record_analysis_failure(db, job_pk, exc)
        raise
    finally:
        db.close()
        engine.dispose()


def _record_analysis_failure(db, job_pk: uuid.UUID | None, exc: Exception) -> None:
    """Persist a safe FAILED state unless the job already reached a terminal state.

    The pipeline records FAILED for failures inside it; this covers everything
    before/around it (DB setup, token refresh, client construction) so an inline
    thread can never leave a job silently QUEUED or RUNNING.
    """
    if job_pk is None:
        return
    try:
        db.rollback()
        job = db.get(AnalysisJob, job_pk)
        if job is None or job.status in AnalysisJobStatus.terminal():
            return
        job.status = AnalysisJobStatus.FAILED.value
        job.error_code = type(exc).__name__  # safe identifier, no payload
        job.error_message = str(exc)[:500]
        job.completed_at = utcnow()
        db.commit()
        logger.warning(
            "analysis failed before pipeline",
            extra={
                "event": "analysis_failed",
                "job_id": str(job_pk),
                "error_type": type(exc).__name__,
            },
        )
    except Exception:  # noqa: BLE001 - never mask the original failure
        logger.exception(
            "failed to record analysis failure",
            extra={"event": "analysis_failure_record_error", "job_id": str(job_pk)},
        )


def execute_cleanup_job(plan_id: str, *, gmail=None) -> None:
    """Execute an approved cleanup plan against Gmail (or an injected client)."""
    import uuid

    settings = get_settings()
    engine, session_factory = create_engine_and_sessionmaker(
        settings.normalized_database_url
    )
    db = session_factory()
    try:
        plan_pk = uuid.UUID(str(plan_id))
        if gmail is None:
            from app.cleanup.service import approve_plan  # noqa: F401 - contract ref
            from app.models import CleanupPlan

            plan = db.get(CleanupPlan, plan_pk)
            if plan is None:
                raise ValueError(f"CleanupPlan {plan_id} not found")
            user = db.get(User, plan.user_id)
            access_token = get_valid_access_token(
                db, user=user, secret_key=settings.effective_secret_key(), settings=settings
            )
            gmail = GoogleGmailClient(access_token, settings)
        try:
            execute_approved_plan(db, plan_id=plan_pk, gmail=gmail)
        finally:
            close = getattr(gmail, "close", None)
            if close is not None:
                close()
    finally:
        db.close()
        engine.dispose()
