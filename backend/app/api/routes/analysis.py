"""Analysis job endpoints: start a run, poll its progress."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.models import AnalysisJob, Mailbox, OAuthConnection, User
from app.models.enums import AnalysisJobStatus, OAuthStatus
from app.workers.dispatcher import dispatch_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_ACTIVE_STATUSES = [s.value for s in AnalysisJobStatus if s not in AnalysisJobStatus.terminal()]


def _connected_mailbox(db: Session, user: User) -> Mailbox:
    connection = db.query(OAuthConnection).filter_by(user_id=user.id).one_or_none()
    if connection is None or connection.status != OAuthStatus.ACTIVE:
        from app.core.errors import ValidationAppError

        raise ValidationAppError("Gmail is not connected. Connect the account first.")
    mailbox = db.query(Mailbox).filter_by(user_id=user.id).one_or_none()
    if mailbox is None:
        from app.core.errors import ValidationAppError

        raise ValidationAppError(
            "No analyzed mailbox yet. Start an analysis to populate your dashboard."
        )
    return mailbox


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
    mailbox = _connected_mailbox(db, user)

    running = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.mailbox_id == mailbox.id,
            AnalysisJob.status.in_(_ACTIVE_STATUSES),
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

    task_ref = dispatch_analysis(str(job.id), settings=settings)
    job.dispatcher_task_id = None if task_ref == "inline" else task_ref
    db.commit()

    return {
        "job_id": str(job.id),
        "status": str(job.status),
        "dispatched_to": task_ref or "inline",
        "poll": f"/api/analysis/jobs/{job.id}",
    }


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
