"""Pytest fixtures: hermetic settings, disposable database, TestClient.

Every fixture builds its own world:

* ``settings``   -> explicit Settings (init kwargs override any local .env),
                    pointing at a throwaway SQLite file in tmp_path.
* ``db_engine``  -> schema created via metadata.create_all (no migrations in
                    unit tests; migrations are exercised in CI against Postgres).
* ``app/client`` -> FastAPI app wired to those settings; TestClient triggers
                    the lifespan so app.state gets engines/redis.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine_and_sessionmaker
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

_TEST_SECRET = "unit-test-secret-0123456789abcdef-0123456789abcdef"


def make_test_settings(**overrides: str) -> Settings:
    """Explicit-kwargs settings factory. Hermetic: ignores local .env files."""
    values: dict = {
        "ENVIRONMENT": "test",
        "SECRET_KEY": _TEST_SECRET,
        "LOG_LEVEL": "WARNING",
        "DEBUG": False,
        "BASE_URL": "http://testserver",
        "FRONTEND_ORIGINS": "http://localhost:3000",
        "DATABASE_URL": "",
        "REDIS_URL": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ANTHROPIC_API_KEY": "",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    db_file = tmp_path / "test-mail-sweep.db"
    return make_test_settings(DATABASE_URL=f"sqlite:///{db_file.as_posix()}")


@pytest.fixture()
def db_engine(settings: Settings) -> Iterator[Engine]:
    engine, _ = create_engine_and_sessionmaker(settings.normalized_database_url)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def app(settings: Settings, db_engine: Engine) -> FastAPI:
    # db_engine pre-created the schema; the app's lifespan opens its own
    # engine/connection to the same throwaway file.
    return create_app(settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def build_world(tmp_path: Path):
    """Factory for worlds with custom settings.

    Returns ``build(**overrides) -> (settings, TestClient, Engine)`` where the
    client is already inside its lifespan context.
    """
    created: list[tuple[TestClient, Any]] = []

    def _build(**overrides: str) -> tuple[Settings, TestClient, Any]:
        db_file = tmp_path / f"world-{len(created)}.db"
        world_settings = make_test_settings(
            DATABASE_URL=f"sqlite:///{db_file.as_posix()}", **overrides
        )
        engine, _ = create_engine_and_sessionmaker(world_settings.normalized_database_url)
        Base.metadata.create_all(engine)

        application = create_app(world_settings)
        test_client = TestClient(application)
        test_client.__enter__()
        created.append((test_client, engine))
        return world_settings, test_client, engine

    try:
        yield _build
    finally:
        for client_, engine in created:
            client_.__exit__(None, None, None)
            engine.dispose()
