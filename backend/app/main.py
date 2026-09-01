"""MailSweep AI - FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis as redis_lib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app import __version__
from app.api.routes.analysis import router as analysis_router
from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.cleanup import router as cleanup_router
from app.api.routes.groups import router as groups_router
from app.api.routes.health import router as health_router
from app.api.routes.mailbox import router as mailbox_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.rules import router as rules_router
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
    """Create/teardown infrastructure clients."""

    settings: Settings = app.state.settings

    engine, sessionmaker = create_engine_and_sessionmaker(
        settings.normalized_database_url
    )

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
        # Development/test: no broker.
        app.state.redis = None

    yield

    if app.state.redis is not None:
        try:
            app.state.redis.close()
        except Exception:  # noqa: BLE001
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

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    app.add_middleware(
        CsrfOriginMiddleware,
        allowed_origins=[
            resolved.BASE_URL,
            *resolved.cors_allowed_origins,
        ],
    )

    app.add_middleware(RequestContextMiddleware)

    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    install_error_handlers(app)

    # ------------------------------------------------------------------
    # Root
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": resolved.APP_NAME,
            "version": __version__,
            "docs": "/docs",
            "health": "/api/health",
        }

    # ------------------------------------------------------------------
    # Google Search Console verification
    # ------------------------------------------------------------------

    @app.get(
        "/google0134155178fa519f.html",
        include_in_schema=False,
        response_class=PlainTextResponse,
    )
    def google_site_verification() -> str:
        return "google-site-verification: google0134155178fa519f.html"

    # ------------------------------------------------------------------
    # API routers
    # ------------------------------------------------------------------

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(cleanup_router)
    app.include_router(analysis_router)
    app.include_router(mailbox_router)
    app.include_router(groups_router)
    app.include_router(recommendations_router)
    app.include_router(rules_router)
    app.include_router(audit_router)

    return app


app = create_app()
