"""Celery application factory (production only).

Built lazily: importing this module never requires Redis. The API/dispatcher
calls :func:`get_celery_app` only when ``REDIS_URL`` is configured.
"""

from __future__ import annotations

from functools import lru_cache

from celery import Celery

from app.core.config import Settings


def make_celery_app(settings: Settings) -> Celery:
    app = Celery(
        "mailsweep",
        broker=settings.REDIS_URL,
    )
    app.conf.update(
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        worker_max_tasks_per_child=100,
    )

    from app.workers.tasks import execute_analysis_job, execute_cleanup_job

    @app.task(name="analysis.run")
    def analysis_run(job_id: str) -> None:
        execute_analysis_job(job_id)

    @app.task(name="cleanup.run")
    def cleanup_run(plan_id: str) -> None:
        execute_cleanup_job(plan_id)

    return app


@lru_cache(maxsize=1)
def get_celery_app(settings_key: str = "") -> Celery:
    """Cached accessor. ``settings_key`` only defeats lru_cache in tests."""
    from app.core.config import get_settings

    return make_celery_app(get_settings())
