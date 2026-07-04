"""Tests for playlist/channel batch job submission."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from app.config import Settings
from app.db import get_async_session_factory, init_db
from app.services.jobs import (
    BatchJobSubmitParams,
    get_jobs_list,
    submit_batch,
)
from app.services.ytdlp import PlaylistEntry


@pytest.fixture
def batch_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, default_settings: Settings):
    """Isolated SQLite DB for submit_batch unit tests."""
    db_path = tmp_path / "batch-job.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("MAX_PLAYLIST_ENTRIES", "100")

    import app.config as cfg_module
    import app.db as db_module

    cfg_module._settings = None
    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr("app.services.jobs.enqueue_job_task", lambda _job_id: "rq-batch-1")
    monkeypatch.setattr("app.services.jobs.update_job_status", _noop)
    return Settings()


def _entries(*ids: str) -> list[PlaylistEntry]:
    return [
        PlaylistEntry(
            id=video_id,
            title=f"Title {video_id}",
            url=f"https://www.youtube.com/watch?v={video_id}",
            uploader="Host",
        )
        for video_id in ids
    ]


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
            (video_id, "existing-job", f"https://www.youtube.com/watch?v={video_id}", "Old"),
        )
        conn.commit()


@pytest.mark.asyncio
async def test_submit_batch_creates_jobs_sharing_batch_id(batch_db: Settings):
    await init_db()
    factory = get_async_session_factory()
    async with factory() as session:
        result = await submit_batch(
            session,
            batch_db,
            BatchJobSubmitParams(
                source_url="https://www.youtube.com/playlist?list=PL123",
                source_type="playlist",
                batch_title="My Playlist",
                entries=_entries("v1", "v2", "v3"),
                destination_folder="podcasts",
            ),
        )

    assert result.created == 3
    assert result.skipped_duplicate == 0
    assert result.failed == 0
    assert len(result.job_ids) == 3

    async with factory() as session:
        items = await get_jobs_list(session)
        assert len(items) == 1
        assert items[0].kind == "batch"
        assert items[0].batch is not None
        assert items[0].batch.id == result.batch_id
        assert items[0].batch.title == "My Playlist"
        assert items[0].total_count == 3
        assert {job.batch_id for job in items[0].jobs} == {result.batch_id}


@pytest.mark.asyncio
async def test_submit_batch_skips_duplicates_without_aborting(batch_db: Settings):
    await init_db()
    _seed_imported_video("dup1")

    factory = get_async_session_factory()
    async with factory() as session:
        result = await submit_batch(
            session,
            batch_db,
            BatchJobSubmitParams(
                source_url="https://www.youtube.com/playlist?list=PL123",
                source_type="playlist",
                batch_title="Mixed",
                entries=_entries("dup1", "fresh1", "fresh2"),
            ),
        )

    assert result.created == 2
    assert result.skipped_duplicate == 1
    assert result.failed == 0
    assert len(result.job_ids) == 2


@pytest.mark.asyncio
async def test_submit_batch_enforces_max_entries_cap(batch_db: Settings, monkeypatch):
    await init_db()
    monkeypatch.setenv("MAX_PLAYLIST_ENTRIES", "2")
    import app.config as cfg_module

    cfg_module._settings = None
    settings = Settings()

    factory = get_async_session_factory()
    async with factory() as session:
        with pytest.raises(ValueError, match="Too many videos selected"):
            await submit_batch(
                session,
                settings,
                BatchJobSubmitParams(
                    source_url="https://www.youtube.com/playlist?list=PL123",
                    source_type="playlist",
                    batch_title="Too many",
                    entries=_entries("a", "b", "c"),
                ),
            )


@pytest.mark.asyncio
async def test_submit_batch_creates_folder_once(batch_db: Settings):
    await init_db()
    folder_name = "batch-folder"
    factory = get_async_session_factory()
    async with factory() as session:
        result = await submit_batch(
            session,
            batch_db,
            BatchJobSubmitParams(
                source_url="https://www.youtube.com/@channel",
                source_type="channel",
                batch_title="Channel",
                entries=_entries("c1", "c2"),
                new_folder=folder_name,
            ),
        )

    assert result.created == 2
    assert (batch_db.output_root / folder_name).is_dir()

    async with factory() as session:
        items = await get_jobs_list(session)
        assert items[0].jobs[0].destination_folder == folder_name
        assert items[0].jobs[1].destination_folder == folder_name


@pytest.mark.asyncio
async def test_submit_batch_rejects_empty_selection(batch_db: Settings):
    await init_db()
    factory = get_async_session_factory()
    async with factory() as session:
        with pytest.raises(ValueError, match="at least one video"):
            await submit_batch(
                session,
                batch_db,
                BatchJobSubmitParams(
                    source_url="https://www.youtube.com/playlist?list=PL123",
                    source_type="playlist",
                    batch_title="Empty",
                    entries=[],
                ),
            )


@pytest.mark.asyncio
async def test_get_jobs_list_keeps_standalone_jobs(batch_db: Settings):
    await init_db()
    from app.services.jobs import JobSubmitParams, submit_job

    factory = get_async_session_factory()
    async with factory() as session:
        await submit_job(
            session,
            batch_db,
            JobSubmitParams(
                url="https://www.youtube.com/watch?v=solo1",
                video_id="solo1",
                validate_url=False,
            ),
        )
        await submit_batch(
            session,
            batch_db,
            BatchJobSubmitParams(
                source_url="https://www.youtube.com/playlist?list=PL123",
                source_type="playlist",
                batch_title="Batch",
                entries=_entries("b1", "b2"),
            ),
        )

    async with factory() as session:
        items = await get_jobs_list(session)
        kinds = [item.kind for item in items]
        assert kinds.count("batch") == 1
        assert kinds.count("job") == 1
