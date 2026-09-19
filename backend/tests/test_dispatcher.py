"""Job dispatch mode tests (``JOB_DISPATCH_MODE``).

Verifies the three modes - auto/inline/celery - for both analysis and cleanup
dispatch without a real Redis server or Celery broker:

* ``"inline"`` uses the existing in-process background thread,
* ``"celery"`` calls (a mocked) ``get_celery_app().send_task``,
* ``"auto"`` preserves the legacy rule: Celery iff ``REDIS_URL`` is set.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.workers import dispatcher
from pydantic import ValidationError

from tests.conftest import make_test_settings

_REDIS = "redis://redis.example.com:6379/0"


class _FakeThread:
    """Placeholder thread that records the dispatch without starting work."""

    instances: list[_FakeThread] = []

    def __init__(self, target, args=(), name=None, daemon=None):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.started = False
        type(self).instances.append(self)

    def start(self) -> None:
        self.started = True


class _FakeAsyncResult:
    def __init__(self, task_id: str) -> None:
        self.id = task_id


class _FakeCeleryApp:
    """Records send_task calls and returns fake AsyncResult objects."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def send_task(self, name: str, args=None):
        self.calls.append((name, list(args or [])))
        return _FakeAsyncResult(f"mocked-task-{len(self.calls)}")


@pytest.fixture()
def fake_thread(monkeypatch):
    """Replace the dispatcher's threading module so no real thread starts."""
    _FakeThread.instances.clear()
    monkeypatch.setattr(dispatcher, "threading", SimpleNamespace(Thread=_FakeThread))
    yield _FakeThread.instances


@pytest.fixture()
def fake_celery(monkeypatch):
    """Mock the lazily-imported Celery app factory used by the dispatcher."""
    app = _FakeCeleryApp()
    monkeypatch.setattr("app.workers.celery_app.get_celery_app", lambda: app)
    return app


def test_default_dispatch_mode_is_auto():
    assert make_test_settings().JOB_DISPATCH_MODE == "auto"


def test_auto_mode_dispatches_inline_without_redis(fake_thread):
    settings = make_test_settings(REDIS_URL="")
    assert dispatcher.dispatch_analysis("job-1", settings=settings) == "inline"
    assert len(fake_thread) == 1
    assert fake_thread[0].started is True
    assert fake_thread[0].target is dispatcher._run_inline_safely
    assert fake_thread[0].args == ("job-1",)


def test_auto_mode_dispatches_celery_with_redis(fake_celery):
    settings = make_test_settings(REDIS_URL=_REDIS)
    task_ref = dispatcher.dispatch_analysis("job-2", settings=settings)
    assert fake_celery.calls == [("analysis.run", ["job-2"])]
    assert task_ref == "mocked-task-1"


def test_inline_mode_uses_inline_thread_even_with_redis(fake_thread):
    settings = make_test_settings(REDIS_URL=_REDIS, JOB_DISPATCH_MODE="inline")
    assert dispatcher.dispatch_analysis("job-3", settings=settings) == "inline"
    assert len(fake_thread) == 1
    assert fake_thread[0].target is dispatcher._run_inline_safely


def test_celery_mode_uses_celery_with_redis(fake_celery):
    settings = make_test_settings(REDIS_URL=_REDIS, JOB_DISPATCH_MODE="celery")
    task_ref = dispatcher.dispatch_analysis("job-4", settings=settings)
    assert fake_celery.calls == [("analysis.run", ["job-4"])]
    assert task_ref == "mocked-task-1"


def test_cleanup_inline_mode_uses_inline_thread_even_with_redis(fake_thread):
    settings = make_test_settings(REDIS_URL=_REDIS, JOB_DISPATCH_MODE="inline")
    assert dispatcher.dispatch_cleanup("plan-1", settings=settings) == "inline"
    assert len(fake_thread) == 1
    assert fake_thread[0].target is dispatcher._run_cleanup_safely
    assert fake_thread[0].args == ("plan-1",)


def test_cleanup_celery_mode_uses_celery_with_redis(fake_celery):
    settings = make_test_settings(REDIS_URL=_REDIS, JOB_DISPATCH_MODE="celery")
    task_ref = dispatcher.dispatch_cleanup("plan-2", settings=settings)
    assert fake_celery.calls == [("cleanup.run", ["plan-2"])]
    assert task_ref == "mocked-task-1"


def test_cleanup_auto_mode_without_redis_uses_inline(fake_thread):
    settings = make_test_settings(REDIS_URL="")
    assert dispatcher.dispatch_cleanup("plan-3", settings=settings) == "inline"


def test_cleanup_auto_mode_with_redis_uses_celery(fake_celery):
    settings = make_test_settings(REDIS_URL=_REDIS)
    task_ref = dispatcher.dispatch_cleanup("plan-4", settings=settings)
    assert fake_celery.calls == [("cleanup.run", ["plan-4"])]
    assert task_ref == "mocked-task-1"


def test_invalid_dispatch_mode_is_rejected():
    with pytest.raises(ValidationError):
        make_test_settings(JOB_DISPATCH_MODE="bogus")
    with pytest.raises(ValidationError):
        make_test_settings(JOB_DISPATCH_MODE="INLINE")  # case-sensitive
