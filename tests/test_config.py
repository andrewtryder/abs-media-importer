"""Tests for config loading: YAML merge and env override."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.config import Settings
from pydantic import ValidationError


def test_defaults(monkeypatch: pytest.MonkeyPatch):
    """Default settings are set correctly."""
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    s = Settings()
    assert s.app_host == "0.0.0.0"
    assert s.app_port == 8080
    assert s.allow_playlists is False
    assert s.allow_channels is False
    assert s.dry_run is False
    assert s.retry_max == 3
    assert s.ytdlp_audio_format == "m4a"
    assert s.collision_mode == "append_id"


def test_env_override(monkeypatch: pytest.MonkeyPatch):
    """Environment variables override defaults."""
    monkeypatch.setenv("APP_PORT", "9090")
    monkeypatch.setenv("ALLOW_PLAYLISTS", "true")
    monkeypatch.setenv("APP_SECRET_KEY", "mysecret")
    s = Settings()
    assert s.app_port == 9090
    assert s.allow_playlists is True


def test_ytdlp_extra_args_from_env(monkeypatch: pytest.MonkeyPatch):
    """Space-separated YTDLP_EXTRA_ARGS string is parsed to list."""
    monkeypatch.setenv("YTDLP_EXTRA_ARGS", "--verbose --no-warnings")
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    s = Settings()
    assert s.ytdlp_extra_args == ["--verbose", "--no-warnings"]


def test_retry_intervals_from_env(monkeypatch: pytest.MonkeyPatch):
    """Comma-separated RETRY_INTERVAL_SECONDS is parsed to int list."""
    monkeypatch.setenv("RETRY_INTERVAL_SECONDS", "30,120,600")
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    s = Settings()
    assert s.retry_interval_seconds == [30, 120, 600]


def test_folder_name_fallbacks_from_env(monkeypatch: pytest.MonkeyPatch):
    """Comma-separated FOLDER_NAME_FALLBACKS is parsed."""
    monkeypatch.setenv("FOLDER_NAME_FALLBACKS", "channel,uploader")
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    s = Settings()
    assert s.folder_name_fallbacks == ["channel", "uploader"]


def test_invalid_collision_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    monkeypatch.setenv("COLLISION_MODE", "bogus")
    with pytest.raises(ValidationError):
        Settings()


def test_yaml_loading_returns_empty_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "nonexistent.yaml"))
    import app.config as cfg_module

    saved = cfg_module._CONFIG_YAML_PATH
    cfg_module._CONFIG_YAML_PATH = tmp_path / "nonexistent.yaml"
    try:
        result = cfg_module._load_yaml()
        assert result == {}
    finally:
        cfg_module._CONFIG_YAML_PATH = saved


def test_yaml_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = {
        "app": {"port": 7777, "auth_enabled": True},
        "paths": {"output_root": "/tmp/test-output"},
        "download": {"allow_playlists": True, "audio_format": "opus"},
    }
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(config))

    import app.config as cfg_module

    saved = cfg_module._CONFIG_YAML_PATH
    cfg_module._CONFIG_YAML_PATH = cfg_file
    try:
        flat = cfg_module._load_yaml()
    finally:
        cfg_module._CONFIG_YAML_PATH = saved

    assert flat.get("APP_PORT") == 7777
    assert flat.get("AUTH_ENABLED") is True
    assert flat.get("OUTPUT_ROOT") == "/tmp/test-output"
    assert flat.get("ALLOW_PLAYLISTS") is True
    assert flat.get("YTDLP_AUDIO_FORMAT") == "opus"


def test_abs_configured_property(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ABS_BASE_URL", "http://abs:13378")
    monkeypatch.setenv("ABS_API_TOKEN", "mytoken")
    monkeypatch.setenv("ABS_LIBRARY_ID", "lib123")
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    s = Settings()
    assert s.abs_configured is True


def test_abs_not_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ABS_BASE_URL", raising=False)
    monkeypatch.delenv("ABS_API_TOKEN", raising=False)
    monkeypatch.delenv("ABS_LIBRARY_ID", raising=False)
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    s = Settings()
    assert s.abs_configured is False


def test_sync_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////data/app.db")
    s = Settings()
    assert "aiosqlite" not in s.sync_database_url
    assert s.sync_database_url == "sqlite:////data/app.db"
