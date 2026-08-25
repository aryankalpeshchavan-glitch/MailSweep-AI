"""Task bodies shared by Celery and the inline dispatcher."""

from __future__ import annotations

import logging
import uuid

from app.analysis.pipeline import run_mailbox_analysis
from app.auth.tokens import get_valid_access_token
from app.core.config import get_settings
from app.db.session import create_engine_and_sessionmaker
from app.gmail.client import GoogleGmailClient
from app.models import AnalysisJob, User

logger = logging.getLogger(__name__)


def execute_analysis_job(job_id: str) -> None:
    """Own everything needed for one analysis run, then clean up.

    Workers are separate processes: they construct their own engine/session,
    refresh the access token if stale, bind a Gmail client, and hand both to
    the pipeline. All failure handling lives inside the pipeline.
    """
    settings = get_settings()
    engine, session_factory = create_engine_and_sessionmaker(
        settings.normalized_database_url
    )
    db = session_factory()
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
            run_mailbox_analysis(db, job_id=job_pk, gmail=gmail, settings=settings)
        finally:
            gmail.close()
    finally:
        db.close()
        engine.dispose()
