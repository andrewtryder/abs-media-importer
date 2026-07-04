"""Database engine and session factory."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator

from sqlalchemy import Boolean, DateTime, Integer, String, Text, inspect, text
from sqlalchemy import create_engine as _sync_create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.schema import Column

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Async engine (FastAPI app)
# ---------------------------------------------------------------------------

_async_engine = None
_async_session_factory = None


def get_async_engine() -> AsyncEngine:
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        _async_engine = create_async_engine(
            settings.database_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


def _default_sql_for_column(column: Column[object]) -> str:
    """Return a SQLite DEFAULT clause for additive columns on existing tables."""
    default = column.default
    if default is not None and getattr(default, "is_scalar", False):
        value = getattr(default, "arg", None)
        if isinstance(value, bool):
            return f" DEFAULT {int(value)}"
        if isinstance(value, int | float):
            return f" DEFAULT {value}"
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f" DEFAULT '{escaped}'"

    if column.nullable:
        return ""

    # NOT NULL columns need a default when added to a table that already has rows.
    if isinstance(column.type, Boolean):
        return " DEFAULT 0"
    if isinstance(column.type, Integer):
        return " DEFAULT 0"
    if isinstance(column.type, DateTime):
        return " DEFAULT CURRENT_TIMESTAMP"
    if isinstance(column.type, String | Text):
        return " DEFAULT ''"
    return ""


def _add_missing_columns(connection: Connection) -> None:
    """Add model columns that are missing from existing tables.

    ``create_all`` only creates missing tables; it does not alter existing ones.
    """
    inspector = inspect(connection)
    dialect = connection.dialect
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            type_sql = column.type.compile(dialect=dialect)
            default_sql = _default_sql_for_column(column)
            connection.execute(
                text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {type_sql}{default_sql}")
            )
            logger.info("Added column %s.%s", table.name, column.name)


def _drop_alembic_version(connection: Connection) -> None:
    """Remove leftover Alembic bookkeeping from older installs."""
    inspector = inspect(connection)
    if inspector.has_table("alembic_version"):
        connection.execute(text("DROP TABLE alembic_version"))
        logger.info("Dropped obsolete alembic_version table")


def _init_schema(connection: Connection) -> None:
    """Create missing tables and columns from SQLAlchemy models."""
    Base.metadata.create_all(bind=connection)
    _add_missing_columns(connection)
    _drop_alembic_version(connection)


async def init_db() -> None:
    """Create or update the database schema from models."""
    engine = get_async_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_init_schema)
    except Exception as exc:
        print(f"Database schema init failed: {exc}", file=sys.stderr, flush=True)
        logger.exception("Database schema init failed")
        raise


# ---------------------------------------------------------------------------
# Sync engine (RQ worker — no event loop)
# ---------------------------------------------------------------------------

_sync_engine = None
_sync_session_factory = None


def get_sync_engine() -> Engine:
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        _sync_engine = _sync_create_engine(
            settings.sync_database_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _sync_engine


def get_sync_session_factory() -> sessionmaker[Session]:
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(get_sync_engine(), expire_on_commit=False)
    return _sync_session_factory


def get_sync_db() -> Session:
    """Return a new sync session. Caller is responsible for closing."""
    return get_sync_session_factory()()
