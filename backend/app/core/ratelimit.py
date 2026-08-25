"""Redis-backed sliding-window rate limiting.

Production requires Redis (validated at startup), where limits are enforced
globally across workers. Development without Redis degrades to unlimited -
documented, logged once, never silently assumed in production.
"""

from __future__ import annotations

import logging

from fastapi import Request

from app.core.errors import RateLimitedError

logger = logging.getLogger(__name__)

_warned = False


def _warn_once() -> None:
    global _warned  # noqa: PLW0603
    if not _warned:
        logger.warning(
            "rate limiting disabled: Redis not configured (development mode)",
            extra={"event": "rate_limit_disabled"},
        )
        _warned = True


def rate_limit(*, name: str, limit: int, window_seconds: int = 60):
    """Dependency factory: max ``limit`` hits per window per client IP."""

    def dependency(request: Request) -> None:
        settings = getattr(request.app.state, "settings", None)
        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            if settings and settings.is_production:
                logger.error(
                    "rate limiter unavailable in production",
                    extra={"event": "rate_limit_missing"},
                )
            _warn_once()
            return

        client_ip = request.client.host if request.client else "unknown"
        bucket = f"ratelimit:{name}:{client_ip}"
        pipe = redis.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, window_seconds)
        count, _ = pipe.execute()
        if int(count) > limit:
            raise RateLimitedError(
                f"Rate limit exceeded ({limit} per {window_seconds}s). Try again shortly."
            )

    return dependency
