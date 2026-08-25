"""Job dispatch: Celery when Redis exists, inline threads otherwise (ADR-0005).

The rest of the application calls :func:`dispatch_analysis` and never learns
which backend ran the job. Inline mode keeps local development on Windows
fully functional without Docker/Redis; production always configures Redis.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import Settings, get_settings
from app.workers.tasks import execute_analysis_job, execute_cleanup_job

logger = logging.getLogger(__name__)

_INLINE_MARKER = "inline"


def dispatch_analysis(job_id: str, *, settings: Settings | None = None) -> str | None:
    """Queue an analysis job. Returns a backend task id (or 'inline')."""
    resolved = settings or get_settings()

    if not resolved.REDIS_URL:
        thread = threading.Thread(
            target=_run_inline_safely, args=(job_id,),
            name=f"analysis-{job_id[:8]}", daemon=True,
        )
        thread.start()
        return _INLINE_MARKER

    # Lazy import: Celery/Redis are only needed on the production path.
    from app.workers.celery_app import get_celery_app

    async_result = get_celery_app().send_task("analysis.run", args=[job_id])
    return str(async_result.id)


def _run_inline_safely(job_id: str) -> None:
    """Pipeline converts failures into job state; this guard is belt-and-braces."""
    try:
        execute_analysis_job(job_id)
    except Exception:  # noqa: BLE001 - background thread must never crash loudly
        logger.exception(
            "inline analysis crashed", extra={"event": "inline_crash", "job_id": job_id}
        )


def run_inline_blocking(job_id: str) -> None:
    """Synchronous execution for tests and scripts."""
    execute_analysis_job(job_id)


def dispatch_cleanup(plan_id: str, *, settings: Settings | None = None) -> str | None:
    """Queue cleanup execution. Same backend choice as analysis jobs."""
    resolved = settings or get_settings()

    if not resolved.REDIS_URL:
        thread = threading.Thread(
            target=_run_cleanup_safely, args=(plan_id,),
            name=f"cleanup-{plan_id[:8]}", daemon=True,
        )
        thread.start()
        return _INLINE_MARKER

    from app.workers.celery_app import get_celery_app

    async_result = get_celery_app().send_task("cleanup.run", args=[plan_id])
    return str(async_result.id)


def run_cleanup_blocking(plan_id: str, *, gmail=None) -> None:
    """Synchronous cleanup execution for tests and scripts."""
    execute_cleanup_job(plan_id, gmail=gmail)


def _run_cleanup_safely(plan_id: str) -> None:
    try:
        execute_cleanup_job(plan_id)
    except Exception:  # noqa: BLE001 - background thread must never crash loudly
        logger.exception(
            "inline cleanup crashed", extra={"event": "inline_cleanup_crash", "plan_id": plan_id}
        )

