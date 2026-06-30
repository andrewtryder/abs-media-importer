"""Database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine as _sync_create_engine
from sqlalchemy.engine import Engine
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
    """Create all tables on startup."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
