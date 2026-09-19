"""Job dispatch: Celery or inline background threads (ADR-0005).

The rest of the application calls :func:`dispatch_analysis` and never learns
which backend ran the job. The backend is selected from
``Settings.JOB_DISPATCH_MODE``:

* ``"auto"``   -> Celery when ``REDIS_URL`` is configured, otherwise the
                  existing in-process background thread (legacy default);
* ``"inline"`` -> always run the job on an in-process background thread
                  (lets a web-only production service work without a worker);
* ``"celery"`` -> always send the job to Celery (dedicated worker).

Inline mode keeps local development on Windows fully functional without
Docker/Redis; ``"inline"`` in production keeps Redis for rate limiting and
health checks while the job runs inside the web process.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import Settings, get_settings
from app.workers.tasks import execute_analysis_job, execute_cleanup_job

logger = logging.getLogger(__name__)

_INLINE_MARKER = "inline"


def _use_celery(resolved: Settings) -> bool:
    """Resolve the dispatch backend for the given settings.

    Explicit ``JOB_DISPATCH_MODE`` values always win; ``"auto"`` preserves
    the legacy rule: Celery iff ``REDIS_URL`` is set.
    """
    if resolved.JOB_DISPATCH_MODE == "inline":
        return False
    if resolved.JOB_DISPATCH_MODE == "celery":
        return True
    return bool(resolved.REDIS_URL)


def dispatch_analysis(job_id: str, *, settings: Settings | None = None) -> str | None:
    """Queue an analysis job. Returns a backend task id (or 'inline')."""
    resolved = settings or get_settings()

    if _use_celery(resolved):
        # Lazy import: Celery/Redis are only needed on the celery path.
        from app.workers.celery_app import get_celery_app

        async_result = get_celery_app().send_task("analysis.run", args=[job_id])
        return str(async_result.id)

    thread = threading.Thread(
        target=_run_inline_safely, args=(job_id,),
        name=f"analysis-{job_id[:8]}", daemon=True,
    )
    thread.start()
    return _INLINE_MARKER


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

    if _use_celery(resolved):
        # Lazy import: Celery/Redis are only needed on the celery path.
        from app.workers.celery_app import get_celery_app

        async_result = get_celery_app().send_task("cleanup.run", args=[plan_id])
        return str(async_result.id)

    thread = threading.Thread(
        target=_run_cleanup_safely, args=(plan_id,),
        name=f"cleanup-{plan_id[:8]}", daemon=True,
    )
    thread.start()
    return _INLINE_MARKER


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

