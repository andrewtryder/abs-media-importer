"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
    """Reset the settings singleton between tests."""
    import app.config as cfg_module

    # Avoid background GitHub release lookups during app lifespan in tests.
    monkeypatch.setenv("ABS_MEDIA_IMPORTER_FETCH_UI_VERSION", "0")

    cfg_module._settings = None
    yield
    cfg_module._settings = None


@pytest.fixture
def tmp_output_root(tmp_path: Path) -> Path:
    root = tmp_path / "podcasts"
    root.mkdir()
    return root


@pytest.fixture
def tmp_work_dir(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    return work


@pytest.fixture
def default_settings(
    tmp_output_root: Path, tmp_work_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    """A Settings instance wired to temp directories via env vars."""
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_PORT", "8080")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////tmp/test.db")
    monkeypatch.setenv("WORK_DIR", str(tmp_work_dir))
    monkeypatch.setenv("ARCHIVE_FILE", str(tmp_work_dir / "archive.txt"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_output_root))
    monkeypatch.setenv("ALLOW_PLAYLISTS", "false")
    monkeypatch.setenv("ALLOW_CHANNELS", "false")
    monkeypatch.setenv("YTDLP_BIN", "yt-dlp")
    monkeypatch.setenv("FFMPEG_BIN", "ffmpeg")
    monkeypatch.setenv("FFPROBE_BIN", "ffprobe")
    monkeypatch.setenv("YTDLP_AUDIO_FORMAT", "m4a")
    monkeypatch.setenv("OUTPUT_EXTENSION", "m4b")
    monkeypatch.setenv("FILENAME_TEMPLATE", "{title}.m4b")
    monkeypatch.setenv("COLLISION_MODE", "append_id")
    monkeypatch.setenv("DRY_RUN", "false")
    return Settings()
