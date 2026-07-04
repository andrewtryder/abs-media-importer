"""Tests for model-driven database schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from app.db import init_db


def _reset_db_engines() -> None:
    import app.db as db_module

    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None


@pytest.fixture
def schema_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolated SQLite database for schema tests."""
    db_path = tmp_path / "schema.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    _reset_db_engines()
    return db_path


@pytest.mark.asyncio
async def test_init_db_creates_schema_on_fresh_database(schema_db: Path):
    await init_db()

    with sqlite3.connect(schema_db) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {
            "jobs",
            "imported_videos",
            "job_attempts",
            "app_settings",
            "import_batches",
        } <= tables
        assert "alembic_version" not in tables

        jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        assert "progress" in jobs_cols
        assert "allow_reimport" in jobs_cols
        assert "batch_id" in jobs_cols

        attempts_cols = {row[1] for row in conn.execute("PRAGMA table_info(job_attempts)")}
        assert "artifact_metadata" in attempts_cols


@pytest.mark.asyncio
async def test_init_db_adds_missing_columns_to_existing_tables(schema_db: Path):
    with sqlite3.connect(schema_db) as conn:
        conn.executescript(
            """
            CREATE TABLE jobs (
                id VARCHAR(36) PRIMARY KEY,
                url TEXT NOT NULL,
                status VARCHAR(14) NOT NULL,
                collision_mode VARCHAR(20) NOT NULL,
                embed_metadata BOOLEAN NOT NULL,
                embed_thumbnail BOOLEAN NOT NULL,
                embed_chapters BOOLEAN NOT NULL,
                trigger_abs_scan BOOLEAN NOT NULL,
                attempts INTEGER NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE job_attempts (
                id VARCHAR(36) PRIMARY KEY,
                job_id VARCHAR(36) NOT NULL,
                attempt_number INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL
            );
            CREATE TABLE imported_videos (
                video_id VARCHAR(64) PRIMARY KEY,
                job_id VARCHAR(36),
                source_url TEXT,
                source_title TEXT,
                imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()

    await init_db()

    with sqlite3.connect(schema_db) as conn:
        jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        assert "progress" in jobs_cols
        assert "allow_reimport" in jobs_cols
        assert "batch_id" in jobs_cols

        attempts_cols = {row[1] for row in conn.execute("PRAGMA table_info(job_attempts)")}
        assert "artifact_metadata" in attempts_cols

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "import_batches" in tables
        assert "app_settings" in tables


@pytest.mark.asyncio
async def test_init_db_is_idempotent(schema_db: Path):
    await init_db()
    await init_db()

    with sqlite3.connect(schema_db) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "jobs" in tables
        assert "import_batches" in tables


@pytest.mark.asyncio
async def test_init_db_drops_obsolete_alembic_version(schema_db: Path):
    with sqlite3.connect(schema_db) as conn:
        conn.executescript(
            """
            CREATE TABLE jobs (
                id VARCHAR(36) PRIMARY KEY,
                url TEXT NOT NULL,
                status VARCHAR(14) NOT NULL,
                collision_mode VARCHAR(20) NOT NULL,
                embed_metadata BOOLEAN NOT NULL,
                embed_thumbnail BOOLEAN NOT NULL,
                embed_chapters BOOLEAN NOT NULL,
                trigger_abs_scan BOOLEAN NOT NULL,
                attempts INTEGER NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL
            );
            INSERT INTO alembic_version (version_num) VALUES ('f2b6d4e83a50');
            """
        )
        conn.commit()

    await init_db()

    with sqlite3.connect(schema_db) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "alembic_version" not in tables
        assert "import_batches" in tables
        jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        assert "batch_id" in jobs_cols


@pytest.mark.asyncio
async def test_init_db_preserves_extra_columns_from_older_builds(schema_db: Path):
    with sqlite3.connect(schema_db) as conn:
        conn.executescript(
            """
            CREATE TABLE jobs (
                id VARCHAR(36) PRIMARY KEY,
                url TEXT NOT NULL,
                status VARCHAR(14) NOT NULL,
                collision_mode VARCHAR(20) NOT NULL,
                embed_metadata BOOLEAN NOT NULL,
                embed_thumbnail BOOLEAN NOT NULL,
                embed_chapters BOOLEAN NOT NULL,
                trigger_abs_scan BOOLEAN NOT NULL,
                attempts INTEGER NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sponsorblock_mark_chapters BOOLEAN NOT NULL DEFAULT 0
            );
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL
            );
            INSERT INTO alembic_version (version_num) VALUES ('f2b6d4e83a50');
            """
        )
        conn.commit()

    await init_db()

    with sqlite3.connect(schema_db) as conn:
        jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        assert "sponsorblock_mark_chapters" in jobs_cols
        assert "batch_id" in jobs_cols
