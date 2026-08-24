"""System routes: health/readiness."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import check_database, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get(
    "/api/health",
    summary="Health / readiness probe",
    description=(
        "Returns component statuses for dependencies. A failing `database` makes "
        "the endpoint return 503. `redis` is reported as `not_configured` in "
        "development (jobs then run inline). Safe for load-balancer probes."
    ),
)
def health(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    settings: Settings = request.app.state.settings
    components: dict[str, dict[str, str]] = {}

    db_ok = check_database(db.get_bind())
    driver = "sqlite" if settings.normalized_database_url.startswith("sqlite") else "postgresql"
    components["database"] = {"status": "ok" if db_ok else "error", "driver": driver}

    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        components["redis"] = {"status": "not_configured"}
    else:
        try:
            redis_client.ping()
            components["redis"] = {"status": "ok"}
        except Exception:  # noqa: BLE001 - health check must not raise
            logger.warning("redis ping failed", extra={"event": "redis_unhealthy"})
            components["redis"] = {"status": "error"}

    body = {
        "status": "ok" if db_ok else "degraded",
        "environment": settings.ENVIRONMENT,
        "components": components,
    }
    return JSONResponse(status_code=200 if db_ok else 503, content=body)
