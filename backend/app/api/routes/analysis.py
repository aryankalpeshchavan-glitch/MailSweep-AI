"""Analysis job endpoints: start a run, poll its progress, resume active jobs."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.core.ratelimit import rate_limit
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AnalysisJob, Mailbox, OAuthConnection, User
from app.models.enums import AnalysisJobStatus, OAuthStatus
from app.workers.dispatcher import dispatch_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _connected_mailbox(db: Session, user: User) -> Mailbox:
    """Resolve the user's mailbox, creating it lazily on the first analysis.

    Google OAuth persists only the User + OAuthConnection (no Mailbox), so the
    dashboard shows "No analyzed mailbox yet" before any run. The Mailbox is
    born here on the first ``POST /api/analysis/start`` and reused afterwards.
    """
    connection = db.query(OAuthConnection).filter_by(user_id=user.id).one_or_none()
    if connection is None or connection.status != OAuthStatus.ACTIVE:
        from app.core.errors import ValidationAppError

        raise ValidationAppError("Gmail is not connected. Connect the account first.")
    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one_or_none()
    if mailbox is None:
        mailbox = Mailbox(
            user_id=user.id,
            google_email_address=connection.google_email,
        )
        db.add(mailbox)
        db.flush()
    return mailbox


def _job_payload(job: AnalysisJob) -> dict:
    """Secret-free job snapshot shared by the poll and active endpoints."""
    percent = (
        round(job.messages_processed / job.messages_total * 100)
        if job.messages_total
        else None
    )
    return {
        "job_id": str(job.id),
        "status": str(job.status),
        "messages_total": job.messages_total,
        "messages_processed": job.messages_processed,
        "progress_percent": percent,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _recover_stale_queued_jobs(db: Session, user_id: uuid.UUID, settings: Settings) -> None:
    """Fail abandoned QUEUED jobs so the user can start a fresh analysis.

    A QUEUED job whose execution never set ``started_at`` within the configured
    timeout was never picked up (or crashed before the pipeline ran). Marking it
    FAILED unblocks the user without manual database changes. A genuinely
    running job is untouched: the pipeline stamps ``started_at`` immediately.
    """
    cutoff = utcnow() - timedelta(seconds=settings.STALE_QUEUED_JOB_TIMEOUT_SECONDS)
    stale = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.user_id == user_id,
            AnalysisJob.status == AnalysisJobStatus.QUEUED.value,
            AnalysisJob.started_at.is_(None),
            AnalysisJob.created_at < cutoff,
        )
        .all()
    )
    for job in stale:
        job.status = AnalysisJobStatus.FAILED.value
        job.error_code = "STALE_QUEUED_JOB"
        job.error_message = (
            "Analysis was never picked up for execution and timed out. "
            "Run analysis again to start a fresh one."
        )
        job.completed_at = utcnow()
        logger.warning(
            "stale queued analysis marked failed",
            extra={"event": "analysis_stale_recovered", "job_id": str(job.id)},
        )
    if stale:
        db.commit()


@router.post(
    "/start",
    status_code=202,
    summary="Start a full-mailbox analysis (asynchronous)",
    dependencies=[Depends(rate_limit(name="analysis_start", limit=5, window_seconds=60))],
    responses={409: {"description": "An analysis is already running"}},
)
def start_analysis(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings: Settings = request.app.state.settings
    _recover_stale_queued_jobs(db, user.id, settings)
    mailbox = _connected_mailbox(db, user)

    running = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.mailbox_id == mailbox.id,
            AnalysisJob.status.in_(AnalysisJobStatus.active_statuses()),
        )
        .one_or_none()
    )
    if running is not None:
        raise ConflictError(
            f"Analysis {running.id} is already {running.status}. Poll it instead."
        )

    job = AnalysisJob(user_id=user.id, mailbox_id=mailbox.id)
    db.add(job)
    db.commit()
    logger.info(
        "analysis created",
        extra={"event": "analysis_created", "job_id": str(job.id)},
    )

    task_ref = dispatch_analysis(str(job.id), settings=settings)
    job.dispatcher_task_id = None if task_ref == "inline" else task_ref
    db.commit()
    logger.info(
        "analysis dispatched",
        extra={
            "event": "analysis_dispatched",
            "job_id": str(job.id),
            "backend": task_ref or "inline",
        },
    )

    return {
        "job_id": str(job.id),
        "status": str(job.status),
        "dispatched_to": task_ref or "inline",
        "poll": f"/api/analysis/jobs/{job.id}",
    }


@router.get("/active", summary="Latest non-terminal analysis job for this user")
def active_analysis(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Answer "what is the latest active analysis?" for dashboard recovery.

    Scoped to the authenticated user; never returns another user's job. Stale
    QUEUED jobs are failed first so a stuck job cannot block a fresh run.
    """
    settings: Settings = request.app.state.settings
    _recover_stale_queued_jobs(db, user.id, settings)
    job = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.user_id == user.id,
            AnalysisJob.status.in_(AnalysisJobStatus.active_statuses()),
        )
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )
    return {"active": _job_payload(job) if job else None}


@router.get("/jobs/{job_id}", summary="Poll analysis progress")
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    job = (
        db.query(AnalysisJob)
        .filter_by(id=job_id, user_id=user.id)
        .one_or_none()
    )
    if job is None:
        raise NotFoundError("Analysis job not found.")
    return _job_payload(job)
