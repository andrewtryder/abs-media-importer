"""Tests for bulk job deletion API behavior."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Use an isolated SQLite DB per test and clear cached engines/settings."""
    db_path = tmp_path / "test-jobs-delete.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    import app.config as cfg_module
    import app.db as db_module

    cfg_module._settings = None
    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _db_path() -> Path:
    db_url = os.environ["DATABASE_URL"]
    prefix = "sqlite+aiosqlite:///"
    if not db_url.startswith(prefix):
        raise AssertionError(f"Unexpected DATABASE_URL in test: {db_url}")
    return Path(db_url.removeprefix(prefix))


def _seed_job(job_id: str, status: str) -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id,
                url,
                collision_mode,
                embed_metadata,
                embed_thumbnail,
                embed_chapters,
                trigger_abs_scan,
                allow_reimport,
                dry_run,
                status,
                attempts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                f"https://www.youtube.com/watch?v={job_id}",
                "append_id",
                1,
                1,
                1,
                0,
                0,
                0,
                status,
                0,
            ),
        )
        conn.commit()


def _seed_imported_video(video_id: str, job_id: str) -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO imported_videos (video_id, job_id, source_url, source_title)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, job_id, f"https://www.youtube.com/watch?v={video_id}", f"Video {video_id}"),
        )
        conn.commit()


def test_bulk_delete_removes_terminal_jobs_and_clears_imported_video_reference(client: TestClient):
    _seed_job("job-succeeded", "succeeded")
    _seed_job("job-failed", "failed")
    _seed_imported_video("video-1", "job-succeeded")

    response = client.post(
        "/api/jobs/delete",
        json={"job_ids": ["job-succeeded", "job-failed"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] == 2
    assert set(payload["deleted_ids"]) == {"job-succeeded", "job-failed"}
    assert payload["missing_ids"] == []

    with sqlite3.connect(_db_path()) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE id IN (?, ?)",
            ("job-succeeded", "job-failed"),
        ).fetchone()[0]
        imported_job_id = conn.execute(
            "SELECT job_id FROM imported_videos WHERE video_id = ?",
            ("video-1",),
        ).fetchone()[0]

    assert remaining == 0
    assert imported_job_id is None


def test_bulk_delete_allows_active_jobs(client: TestClient):
    _seed_job("job-running", "running")
    _seed_job("job-succeeded", "succeeded")

    response = client.post(
        "/api/jobs/delete",
        json={"job_ids": ["job-running", "job-succeeded"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] == 2
    assert set(payload["deleted_ids"]) == {"job-running", "job-succeeded"}
    assert payload["missing_ids"] == []

    with sqlite3.connect(_db_path()) as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE id IN (?, ?)",
            ("job-running", "job-succeeded"),
        ).fetchone()[0]

    assert remaining == 0
