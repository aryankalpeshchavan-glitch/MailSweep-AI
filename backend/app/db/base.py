"""Declarative ORM base shared by every model.

Portability rules (SQLite tests vs PostgreSQL production, ADR-0009):

* ``Uuid`` type - native UUID on Postgres, CHAR(32) on SQLite.
* ``JSON`` instead of ``JSONB``/ARRAY.
* ``Enum(native_enum=False)`` - VARCHAR + CHECK constraints everywhere.
* All datetimes are timezone-aware UTC; :func:`utcnow` is the single clock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """The application clock. Naive datetimes are forbidden."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, sort_order=-100
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, sort_order=900
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        sort_order=901,
    )


# Alembic env and tests can rely on `from app.db.base import Base` receiving
# every model once app.models has been imported at least once.
