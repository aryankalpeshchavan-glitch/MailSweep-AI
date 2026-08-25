"""Retry policy for Gmail API calls.

Rules (spec §13/§28):

* Retry ONLY what is safe: 429 (rate limit) and 5xx transport/server errors,
  plus transient network exceptions. Never retry 4xx client errors.
* Honor Google's ``Retry-After`` header when present, else exponential backoff
  with full jitter (AWS-recommended variant) to avoid thundering herds.
* Bounded attempts; every give-up is logged with the operation name and never
  with response bodies (they may contain user data).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 32.0


def _status_of(exc: Exception) -> int | None:
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "resp", None), "headers", None) or {}
    raw = None
    if isinstance(headers, dict):
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if isinstance(headers, dict) and not raw:
            # httplib2 lowercases keys
            for key, value in headers.items():
                if str(key).lower() == "retry-after":
                    raw = value
                    break
    try:
        return max(float(raw), 0.0) if raw else None
    except (TypeError, ValueError):
        return None


def _is_retryable(exc: Exception) -> bool:
    status = _status_of(exc)
    return status in RETRYABLE_STATUS_CODES


def execute_with_retry[T](
    operation: Callable[[], T],
    *,
    operation_name: str,
    sleep: Callable[[float], None] = time.sleep,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    on_give_up: Callable[[Exception], None] | None = None,
) -> T:
    """Run ``operation()`` with bounded exponential backoff + jitter.

    ``sleep`` is injectable for tests. Non-retryable exceptions propagate
    immediately.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_retryable(exc):
                raise
            last_error = exc
            if attempt == max_attempts:
                break
            retry_after = _retry_after_seconds(exc)
            delay = min(
                MAX_DELAY_SECONDS,
                retry_after or BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
            )
            if retry_after is None:
                delay += random.uniform(0, delay * 0.5)  # full-ish jitter
            logger.info(
                "gmail call retried",
                extra={
                    "event": "gmail_retry",
                    "operation": operation_name,
                    "attempt": attempt,
                    "delay_s": round(delay, 2),
                    "status": _status_of(exc),
                },
            )
            sleep(delay)

    assert last_error is not None  # pragma: no cover - loop guarantees this
    logger.warning(
        "gmail call exhausted retries",
        extra={"event": "gmail_retries_exhausted", "operation": operation_name},
    )
    if on_give_up is not None:
        on_give_up(last_error)
    raise last_error


class RateLimitedError(RuntimeError):
    """Duck-typed 429 error for fakes/tests: carries ``resp.status``/``.headers``."""

    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("Gmail rate limit hit")
        self.resp = _FakeResponse(status=429, retry_after=retry_after)


class ServerUnavailableError(RuntimeError):
    """Duck-typed 503 error for fakes/tests."""

    def __init__(self) -> None:
        super().__init__("Gmail backend unavailable")
        self.resp = _FakeResponse(status=503, retry_after=None)


class _FakeResponse:
    def __init__(self, status: int, retry_after: float | None) -> None:
        self.status = status
        self.headers: dict[str, str] = {"Retry-After": str(retry_after)} if retry_after else {}

