"""MailSweep AI - FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis as redis_lib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.csrf import CsrfOriginMiddleware
from app.core.errors import install_error_handlers
from app.core.logging import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    setup_logging,
)
from app.db.session import create_engine_and_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create/teardown infrastructure clients.

    Deliberately done at startup (not import time) so importing this module is
    side-effect free - important for Alembic, workers and tests.
    """
    settings: Settings = app.state.settings
    engine, sessionmaker = create_engine_and_sessionmaker(settings.normalized_database_url)
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    if settings.REDIS_URL:
        app.state.redis = redis_lib.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    else:
        # Development/test: no broker. Jobs run via the inline dispatcher.
        app.state.redis = None

    yield

    if app.state.redis is not None:
        try:
            app.state.redis.close()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            pass
    engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    setup_logging(resolved.LOG_LEVEL)

    app = FastAPI(
        title=resolved.APP_NAME,
        version=__version__,
        summary="Intelligent, explainable, privacy-conscious Gmail cleanup assistant.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Shared state consumed by dependencies and routes.
    app.state.settings = resolved

    # Middleware ordering: LAST registered = OUTERMOST. Effective chain
    # (outer -> inner): CORS -> SecurityHeaders -> RequestContext -> CSRF -> app.
    # CSRF sits inside RequestContext so its 403s still carry X-Request-ID.
    app.add_middleware(
        CsrfOriginMiddleware,
        allowed_origins=[resolved.BASE_URL, *resolved.cors_allowed_origins],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    install_error_handlers(app)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": resolved.APP_NAME,
            "version": __version__,
            "docs": "/docs",
            "health": "/api/health",
        }

    app.include_router(health_router)
    app.include_router(auth_router)
    return app


app = create_app()
