"""Alembic environment for MailSweep AI.

The migration URL always comes from application configuration (env var /
.env via ``app.core.config``), so there is exactly one source of truth.
A URL passed programmatically (e.g. tests/CI) wins over the environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the backend package importable regardless of invocation directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context  # noqa: E402
from sqlalchemy import engine_from_config, pool  # noqa: E402

import app.models  # noqa: F401,E402 - importing registers every ORM mapper
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402

config = context.config
# Logging is configured by the application itself (app.core.logging);
# alembic's fileConfig-based logging setup is intentionally not used.

target_metadata = Base.metadata


def _database_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url") or ""
    return explicit or get_settings().normalized_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
