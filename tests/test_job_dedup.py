"""Tests for DB-backed duplicate import guard on job creation."""

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
    """Use an isolated SQLite DB per test and clear cached engines."""
    db_path = tmp_path / "test-job-dedup.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    import app.db as db_module

    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create app client with queue side effects stubbed out."""

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr("app.services.jobs.enqueue_job_task", lambda job_id: "rq-job-123")
    monkeypatch.setattr("app.services.jobs.update_job_status", _noop)

    with TestClient(create_app()) as test_client:
        yield test_client


def _seed_imported_video(video_id: str) -> None:
    db_url = os.environ["DATABASE_URL"]
    prefix = "sqlite+aiosqlite:///"
    if not db_url.startswith(prefix):
        raise AssertionError(f"Unexpected DATABASE_URL in test: {db_url}")
    db_path = Path(db_url.removeprefix(prefix))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO imported_videos (video_id, job_id, source_url, source_title)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, "existing-job", "https://www.youtube.com/watch?v=dup123", "Old Title"),
        )
        conn.commit()


def test_api_jobs_rejects_already_imported_video_id(client: TestClient):
    """`/api/jobs` should reject duplicate `video_id` before queueing work."""
    _seed_imported_video("dup123")

    response = client.post(
        "/api/jobs",
        data={
            "url": "https://www.youtube.com/watch?v=dup123",
            "video_id": "dup123",
            "source_title": "Duplicate Video",
        },
    )

    assert response.status_code == 409
    assert "already been imported" in response.text


def test_api_jobs_allows_reimport_when_flag_set(client: TestClient):
    """`/api/jobs` should allow duplicate `video_id` when explicitly requested."""
    _seed_imported_video("dup123")

    response = client.post(
        "/api/jobs",
        data={
            "url": "https://www.youtube.com/watch?v=dup123",
            "video_id": "dup123",
            "source_title": "Duplicate Video",
            "allow_reimport": "true",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
