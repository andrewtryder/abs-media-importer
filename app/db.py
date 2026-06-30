"""Database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine as _sync_create_engine
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base

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


async def init_db() -> None:
    """Create all tables on startup and apply lightweight migrations."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def run_migrations(connection: Connection) -> None:
            # Check jobs columns
            cursor = connection.execute(text("PRAGMA table_info(jobs)"))
            cols = [row[1] for row in cursor.fetchall()]

            new_cols = [
                ("progress", "INTEGER"),
                ("progress_percent", "FLOAT"),
                ("progress_eta", "VARCHAR(32)"),
                ("progress_speed", "VARCHAR(32)"),
                ("progress_label", "VARCHAR(64)"),
            ]

            for col_name, col_type in new_cols:
                if col_name not in cols:
                    connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))

            # Check job_attempts columns
            cursor_attempts = connection.execute(text("PRAGMA table_info(job_attempts)"))
            attempts_cols = [row[1] for row in cursor_attempts.fetchall()]

            if "artifact_metadata" not in attempts_cols:
                connection.execute(
                    text("ALTER TABLE job_attempts ADD COLUMN artifact_metadata TEXT")
                )

        await conn.run_sync(run_migrations)


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
