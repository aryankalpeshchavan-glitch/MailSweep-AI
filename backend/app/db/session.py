"""Engine/session factory and the request-scoped DB dependency.

Engines are created through :func:`create_engine_and_sessionmaker` so that
the API (lifespan), Celery workers, and Alembic can each own their own engine
while sharing identical configuration.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_and_sessionmaker(
    database_url: str, engine_kwargs: dict[str, Any] | None = None
) -> tuple[Engine, sessionmaker]:
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        # FastAPI runs sync endpoints on a threadpool; SQLite must allow it.
        connect_args["check_same_thread"] = False

    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if engine_kwargs:
        kwargs.update(engine_kwargs)

    engine = create_engine(database_url, connect_args=connect_args, **kwargs)

    if database_url.startswith("sqlite"):
        # Production PostgreSQL enforces FKs (CASCADE/SET NULL); make SQLite
        # behave identically so tests exercise real referential integrity.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine, factory


def get_db(request: Request) -> Iterator[Session]:
    """Request-scoped session.

    Services/endpoints commit explicitly when a unit of work succeeds;
    this dependency only guarantees rollback-on-exception and cleanup.
    """
    db: Session = request.app.state.sessionmaker()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health check must not raise
        return False
