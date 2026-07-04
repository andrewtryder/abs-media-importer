from __future__ import annotations

from pathlib import Path

import app.config as config_module
import app.db as db_module
import pytest
from app.config import get_setting_sources, reload_settings, save_settings
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import select


def _reset_runtime_state() -> None:
    config_module._settings = None
    config_module._pinned_sources = {}
    config_module._db_overrides = {}
    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None


@pytest.fixture
def settings_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated data directory and SQLite database for settings tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.delenv("OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("ALLOW_PLAYLISTS", raising=False)
    monkeypatch.delenv("ALLOW_CHANNELS", raising=False)
    monkeypatch.delenv("MAX_PLAYLIST_ENTRIES", raising=False)
    monkeypatch.delenv("ABS_SCAN_AFTER_SUCCESS", raising=False)
    monkeypatch.delenv("YTDLP_EXTRA_ARGS", raising=False)
    monkeypatch.delenv("FFMPEG_EXTRA_ARGS", raising=False)
    monkeypatch.delenv("COLLISION_MODE", raising=False)
    monkeypatch.delenv("FILENAME_TEMPLATE", raising=False)
    monkeypatch.delenv("OUTPUT_EXTENSION", raising=False)
    monkeypatch.setattr(config_module, "_get_default_data_dir", lambda: data_dir)
    monkeypatch.setattr(config_module, "_parse_dotenv_keys", lambda: set())
    _reset_runtime_state()

    import asyncio

    from app.db import init_db

    asyncio.run(init_db())
    reload_settings()
    yield data_dir
    _reset_runtime_state()


def test_save_and_load_custom_settings(settings_env: Path):
    s1 = reload_settings()
    assert s1.output_root == Path("/media/podcasts")

    custom_path = settings_env / "my_custom_podcasts"
    custom_path.mkdir()
    save_settings(
        {
            "output_root": str(custom_path),
            "dry_run": "true",
            "allow_playlists": "true",
            "allow_channels": "true",
            "abs_scan_after_success": "true",
        }
    )

    s2 = reload_settings()
    assert s2.output_root == custom_path
    assert s2.dry_run is True
    assert s2.allow_playlists is True
    assert s2.allow_channels is True
    assert s2.abs_scan_after_success is True

    from app.db import get_sync_session_factory
    from app.models import AppSetting

    with get_sync_session_factory()() as session:
        rows = {row.key: row.value for row in session.scalars(select(AppSetting)).all()}
    assert rows["output_root"] == str(custom_path)
    assert rows["dry_run"] == "true"


def test_get_settings_page(settings_env: Path):
    client = TestClient(app)
    response = client.get("/settings")
    assert response.status_code == 200
    assert "Settings" in response.text
    assert "Output Root Directory" in response.text
    assert "/media/podcasts" in response.text


def test_post_settings_valid(settings_env: Path, tmp_path: Path):
    client = TestClient(app)
    valid_path = tmp_path / "new_output"
    response = client.post(
        "/settings",
        data={
            "output_root": str(valid_path),
            "dry_run": "on",
            "allow_playlists": "on",
            "allow_channels": "on",
            "abs_scan_after_success": "on",
            "collision_mode": "skip",
            "cleanup_temp_on_success": "on",
            "cleanup_temp_on_failure": "on",
            "job_timeout_seconds": "7200",
            "retry_max": "2",
            "retry_interval_seconds": "30,120",
            "max_playlist_entries": "50",
            "output_extension": "m4b",
            "filename_template": "{title}.m4b",
            "folder_name_field": "uploader_id",
            "folder_name_fallbacks": "uploader_id,channel",
            "allowed_domains": "youtube.com,youtu.be",
            "ytdlp_extra_args": "--verbose",
            "ffmpeg_extra_args": "",
            "cookies_file": "",
            "default_destination_folder": "",
        },
    )
    assert response.status_code == 200
    assert "Settings saved successfully" in response.text
    assert str(valid_path) in response.text

    settings = reload_settings()
    assert settings.output_root == valid_path
    assert settings.dry_run is True
    assert settings.collision_mode == "skip"
    assert settings.retry_max == 2
    assert settings.max_playlist_entries == 50


def test_post_settings_relative(settings_env: Path):
    client = TestClient(app)
    response = client.post(
        "/settings",
        data={
            "output_root": "some/relative/path",
            "collision_mode": "append_id",
            "job_timeout_seconds": "10800",
            "retry_max": "3",
            "retry_interval_seconds": "60,300,900",
            "max_playlist_entries": "100",
            "output_extension": "m4b",
            "filename_template": "{title}.m4b",
            "folder_name_field": "uploader_id",
            "folder_name_fallbacks": "uploader_id,channel_id,channel,uploader",
            "allowed_domains": "youtube.com",
        },
    )
    assert response.status_code == 400
    assert "absolute path" in response.text.lower()


def test_post_settings_non_writable(settings_env: Path):
    client = TestClient(app)
    fake_file = settings_env / "not_a_dir"
    fake_file.touch()
    response = client.post(
        "/settings",
        data={
            "output_root": str(fake_file),
            "collision_mode": "append_id",
            "job_timeout_seconds": "10800",
            "retry_max": "3",
            "retry_interval_seconds": "60,300,900",
            "max_playlist_entries": "100",
            "output_extension": "m4b",
            "filename_template": "{title}.m4b",
            "folder_name_field": "uploader_id",
            "folder_name_fallbacks": "uploader_id,channel_id,channel,uploader",
            "allowed_domains": "youtube.com",
        },
    )
    assert response.status_code == 400
    assert "not writable" in response.text.lower()


def test_env_locks_setting_in_ui(settings_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DRY_RUN", "true")
    _reset_runtime_state()
    sources = get_setting_sources()
    assert sources["dry_run"]["locked"] is True
    assert sources["dry_run"]["source"] == "env"


def test_extra_args_reject_shell_injection(settings_env: Path):
    client = TestClient(app)
    valid_path = settings_env / "output"
    valid_path.mkdir()
    response = client.post(
        "/settings",
        data={
            "output_root": str(valid_path),
            "ytdlp_extra_args": "--verbose; rm -rf /",
            "collision_mode": "append_id",
            "job_timeout_seconds": "10800",
            "retry_max": "3",
            "retry_interval_seconds": "60,300,900",
            "max_playlist_entries": "100",
            "output_extension": "m4b",
            "filename_template": "{title}.m4b",
            "folder_name_field": "uploader_id",
            "folder_name_fallbacks": "uploader_id,channel_id,channel,uploader",
            "allowed_domains": "youtube.com",
        },
    )
    assert response.status_code == 400
    assert "shell metacharacters" in response.text.lower()
