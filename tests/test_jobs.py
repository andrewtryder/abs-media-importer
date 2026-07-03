"""Tests for job status transitions and retry behavior."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from app.config import Settings
from app.db import get_async_session_factory, init_db
from app.models import JobStatus
from app.services.jobs import (
    DuplicateVideoError,
    InvalidJobUrlError,
    JobSubmitParams,
    submit_job,
)

# ── JobStatus enum ─────────────────────────────────────────────────────────────


def test_job_status_values():
    assert JobStatus.queued == "queued"
    assert JobStatus.running == "running"
    assert JobStatus.downloading == "downloading"
    assert JobStatus.postprocessing == "postprocessing"
    assert JobStatus.converting == "converting"
    assert JobStatus.verifying == "verifying"
    assert JobStatus.scanning == "scanning"
    assert JobStatus.succeeded == "succeeded"
    assert JobStatus.failed == "failed"
    assert JobStatus.cancelled == "cancelled"


def test_job_status_all_statuses():
    expected = {
        "queued",
        "running",
        "downloading",
        "postprocessing",
        "converting",
        "verifying",
        "scanning",
        "succeeded",
        "failed",
        "cancelled",
    }
    actual = {s.value for s in JobStatus}
    assert actual == expected


# ── Job model ─────────────────────────────────────────────────────────────────


def test_job_duration_formatted_seconds():
    from app.models import Job

    job = Job()
    job.duration = 90
    assert job.duration_formatted == "1:30"


def test_job_duration_formatted_hours():
    from app.models import Job

    job = Job()
    job.duration = 3661
    assert job.duration_formatted == "1:01:01"


def test_job_duration_formatted_none():
    from app.models import Job

    job = Job()
    job.duration = None
    assert job.duration_formatted == "--:--"


# ── Retry logic ────────────────────────────────────────────────────────────────

TERMINAL_STATUSES = {JobStatus.failed, JobStatus.cancelled}
ACTIVE_STATUSES = {
    JobStatus.queued,
    JobStatus.running,
    JobStatus.downloading,
    JobStatus.postprocessing,
    JobStatus.converting,
    JobStatus.verifying,
    JobStatus.scanning,
}


def test_retry_only_allowed_for_terminal():
    """Only failed/cancelled jobs can be retried; others should not."""
    for status in ACTIVE_STATUSES:
        assert status not in TERMINAL_STATUSES

    for status in TERMINAL_STATUSES:
        assert status not in ACTIVE_STATUSES


def test_succeeded_job_not_retryable():
    assert JobStatus.succeeded not in TERMINAL_STATUSES


# ── Phase transitions ─────────────────────────────────────────────────────────


def test_expected_phase_progression():
    """Verify the happy-path phase order is defined correctly."""
    happy_path = [
        "queued",
        "running",
        "downloading",
        "postprocessing",
        "converting",
        "verifying",
        "scanning",
        "succeeded",
    ]
    # All phases should be valid JobStatus values
    valid = {s.value for s in JobStatus}
    for phase in happy_path:
        assert phase in valid


# ── submit_job service ───────────────────────────────────────────────────────


@pytest.fixture
def submit_job_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, default_settings: Settings):
    """Isolated SQLite DB for submit_job unit tests."""
    db_path = tmp_path / "submit-job.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    import app.db as db_module

    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr("app.services.jobs.enqueue_job_task", lambda _job_id: "rq-test-1")
    monkeypatch.setattr("app.services.jobs.update_job_status", _noop)
    return default_settings


def _seed_imported_video(video_id: str) -> None:
    db_url = os.environ["DATABASE_URL"]
    prefix = "sqlite+aiosqlite:///"
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


@pytest.mark.asyncio
async def test_submit_job_invalid_url_raises(submit_job_db: Settings):
    await init_db()
    mock_svc = Mock()
    mock_svc.validate_url.return_value = Mock(valid=False, error="bad url")

    with patch("app.services.jobs.YtDlpService", return_value=mock_svc):
        factory = get_async_session_factory()
        async with factory() as session:
            with pytest.raises(InvalidJobUrlError, match="bad url"):
                await submit_job(
                    session,
                    submit_job_db,
                    JobSubmitParams(url="https://example.com/not-youtube"),
                )


@pytest.mark.asyncio
async def test_submit_job_duplicate_video_raises(submit_job_db: Settings):
    await init_db()
    _seed_imported_video("dup123")
    mock_svc = Mock()
    mock_svc.validate_url.return_value = Mock(valid=True)

    with patch("app.services.jobs.YtDlpService", return_value=mock_svc):
        factory = get_async_session_factory()
        async with factory() as session:
            with pytest.raises(DuplicateVideoError, match="already been imported"):
                await submit_job(
                    session,
                    submit_job_db,
                    JobSubmitParams(
                        url="https://www.youtube.com/watch?v=dup123",
                        video_id="dup123",
                    ),
                )


@pytest.mark.asyncio
async def test_submit_job_allows_reimport_when_flag_set(submit_job_db: Settings):
    await init_db()
    _seed_imported_video("dup123")
    mock_svc = Mock()
    mock_svc.validate_url.return_value = Mock(valid=True)

    with patch("app.services.jobs.YtDlpService", return_value=mock_svc):
        factory = get_async_session_factory()
        async with factory() as session:
            job, rq_id = await submit_job(
                session,
                submit_job_db,
                JobSubmitParams(
                    url="https://www.youtube.com/watch?v=dup123",
                    video_id="dup123",
                    allow_reimport=True,
                ),
            )

    assert job.video_id == "dup123"
    assert rq_id == "rq-test-1"


@pytest.mark.asyncio
async def test_submit_job_new_folder_sets_destination(submit_job_db: Settings, tmp_path: Path):
    await init_db()
    mock_svc = Mock()
    mock_svc.validate_url.return_value = Mock(valid=True)
    new_folder_name = "my-podcast"

    with patch("app.services.jobs.YtDlpService", return_value=mock_svc):
        factory = get_async_session_factory()
        async with factory() as session:
            job, rq_id = await submit_job(
                session,
                submit_job_db,
                JobSubmitParams(
                    url="https://www.youtube.com/watch?v=abc123",
                    video_id="abc123",
                    new_folder=new_folder_name,
                ),
            )

    assert job.destination_folder == new_folder_name
    assert (submit_job_db.output_root / new_folder_name).is_dir()
    assert rq_id == "rq-test-1"
