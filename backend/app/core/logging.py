"""Structured JSON logging with request context.

Design notes
------------
* Standard library ``logging`` only - no extra dependency, no magic.
* A :class:`contextvars.ContextVar` carries ``request_id`` / ``user_id`` so
  every log line inside a request is correlatable without threading values
  through signatures.
* :class:`RedactFilter` is a second line of defense: any record attribute whose
  name looks secret-bearing is replaced before formatting. Callers are still
  expected never to log tokens or email bodies in the first place.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Iterable
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")

_REDACTED_ATTR_NAMES = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "cookie",
    "session_token",
}

# Native LogRecord attributes; anything else on __dict__ came from an
# `extra={...}` and belongs in the JSON payload.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
    }
)


class RedactFilter(logging.Filter):
    """Neutralize obviously sensitive attributes attached to log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        for name in list(record.__dict__):
            if name.lower() in _REDACTED_ATTR_NAMES:
                setattr(record, name, "[REDACTED]")
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, stable field order."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
        }
        payload.update(
            {
                k: v
                for k, v in record.__dict__.items()
                if k not in _RESERVED_RECORD_ATTRS and not k.startswith("_")
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    """Idempotent root-logger configuration."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactFilter())
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)

    # Uvicorn would otherwise double-log in its own format.
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True


def bind_user_id(user_id: Any) -> None:
    user_id_var.set(str(user_id) if user_id else "-")


class RequestContextMiddleware:
    """Pure-ASGI middleware: assigns/propagates ``X-Request-ID`` and emits one
    structured access-log line per request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id")
        rid = (incoming.decode("latin-1")[:64] if incoming else "") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logging.getLogger("mailsweep.access").info(
                "request completed",
                extra={
                    "event": "http_request",
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "http_status": status_holder["status"],
                    "duration_ms": elapsed_ms,
                },
            )
            request_id_var.reset(token)


class SecurityHeadersMiddleware:
    """Conservative security headers appropriate for a JSON API."""

    _HEADERS: Iterable[tuple[bytes, bytes]] = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"same-origin"),
        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
        (b"cache-control", b"no-store"),
    )

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers_mut = message.setdefault("headers", [])
                existing = {k.lower() for k, _ in headers_mut}
                for key, value in self._HEADERS:
                    if key not in existing:
                        headers_mut.append((key, value))
            await send(message)

        await self.app(scope, receive, send_wrapper)

