"""Consistent error responses.

Every client-visible failure is a JSON envelope::

    {
      "error": {"code": "...", "message": "...", "details": {...}?},
      "request_id": "..."
    }

Rules:
* Internal details (stack traces, SQL, provider payloads) NEVER reach the
  client; production returns a generic message for unexpected exceptions.
* Validation errors are sanitized: field locations and messages only - never
  echo back submitted values (they may contain secrets or email content).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

_DEBUG_DETAIL_LIMIT = 2000


class AppError(Exception):
    """Base class for expected, well-mapped application errors."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict | list | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code, code, default_message = 404, "not_found", "Resource not found."


class AuthenticationError(AppError):
    status_code, code, default_message = 401, "unauthorized", "Authentication required."


class AuthorizationError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have access to this resource."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with current state."


class ValidationAppError(AppError):
    status_code, code, default_message = 422, "validation_error", "Request validation failed."


class RateLimitedError(AppError):
    status_code, code, default_message = 429, "rate_limited", "Too many requests. Please slow down."


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"
    default_message = "An upstream service failed."


def _envelope(code: str, message: str, details: dict | list | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error, "request_id": request_id_var.get()}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info(
            "application error",
            extra={"event": "app_error", "error_code": exc.code, "http_status": exc.status_code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", "Request validation failed.", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be processed."
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(f"http_{exc.status_code}", message),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        settings = getattr(app.state, "settings", None)
        debug = bool(settings and getattr(settings, "DEBUG", False)) and not settings.is_production
        logger.exception(
            "unhandled exception",
            extra={"event": "unhandled_exception", "error_type": type(exc).__name__},
        )
        message = str(exc)[:_DEBUG_DETAIL_LIMIT] if debug else "An internal error occurred."
        return JSONResponse(status_code=500, content=_envelope("internal_error", message))
