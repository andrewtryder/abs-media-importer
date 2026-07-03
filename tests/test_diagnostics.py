"""Tests for diagnostics checks and routes."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.config import Settings
from app.diagnostics import (
    DiagnosticCheck,
    check_abs_api,
    check_binary_version,
    check_cookies,
    check_database,
    check_path,
    check_redis,
    diagnostic_groups,
    format_free_space,
)
from app.main import create_app
from app.services.audiobookshelf import ScanResult
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "test-diagnostics.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")

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


def test_format_free_space_returns_label(tmp_path: Path):
    label = format_free_space(tmp_path)
    assert "free" in label.lower()


def test_check_binary_version_ok():
    mock_result = subprocess.CompletedProcess(
        args=["yt-dlp", "--version"],
        returncode=0,
        stdout="2024.10.07\n",
        stderr="",
    )
    with patch("app.diagnostics.subprocess.run", return_value=mock_result):
        check = check_binary_version(
            check_id="ytdlp",
            label="yt-dlp",
            binary="yt-dlp",
            version_args=["--version"],
        )

    assert check.status == "ok"
    assert check.detail == "2024.10.07"


def test_check_binary_version_not_found():
    with patch("app.diagnostics.subprocess.run", side_effect=FileNotFoundError()):
        check = check_binary_version(
            check_id="ytdlp",
            label="yt-dlp",
            binary="missing-bin",
            version_args=["--version"],
        )

    assert check.status == "error"
    assert "not found" in check.summary.lower()


def test_check_redis_ok(default_settings: Settings):
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    with patch("app.diagnostics.Redis.from_url", return_value=mock_client):
        check = check_redis(default_settings)

    assert check.status == "ok"
    mock_client.ping.assert_called_once()


def test_check_redis_connection_error(default_settings: Settings):
    from redis.exceptions import ConnectionError

    with patch("app.diagnostics.Redis.from_url", side_effect=ConnectionError("connection refused")):
        check = check_redis(default_settings)

    assert check.status == "error"


def test_check_database_ok(tmp_path: Path, default_settings: Settings):
    db_path = tmp_path / "nested" / "app.db"
    default_settings.database_url = f"sqlite+aiosqlite:///{db_path}"
    check = check_database(default_settings)

    assert check.status == "ok"
    assert check.path == str(db_path)


def test_check_path_ok(default_settings: Settings):
    check = check_path(
        check_id="output_root",
        label="Output root",
        path=default_settings.output_root,
        create=False,
    )
    assert check.status == "ok"
    assert check.path == str(default_settings.output_root)


def test_check_path_not_writable(tmp_path: Path):
    missing = tmp_path / "missing-output"
    check = check_path(
        check_id="output_root",
        label="Output root",
        path=missing,
        create=False,
    )
    assert check.status == "error"


def test_check_cookies_not_configured(default_settings: Settings):
    default_settings.cookies_file = None
    check = check_cookies(default_settings)
    assert check.status == "warn"


def test_check_cookies_missing_file(default_settings: Settings, tmp_path: Path):
    default_settings.cookies_file = tmp_path / "missing-cookies.txt"
    check = check_cookies(default_settings)
    assert check.status == "error"


def test_check_cookies_readable(default_settings: Settings, tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("cookie data", encoding="utf-8")
    default_settings.cookies_file = cookies
    check = check_cookies(default_settings)
    assert check.status == "ok"


def test_check_abs_api_skipped(default_settings: Settings):
    default_settings.abs_base_url = None
    default_settings.abs_api_token = None
    default_settings.abs_library_id = None
    check = check_abs_api(default_settings)
    assert check.status == "skipped"


def test_check_abs_api_ok(default_settings: Settings):
    default_settings.abs_base_url = "http://abs:13378"
    default_settings.abs_api_token = "token"
    default_settings.abs_library_id = "lib-001"
    with patch(
        "app.diagnostics.AudiobookshelfClient.check_connectivity",
        return_value=ScanResult(success=True),
    ):
        check = check_abs_api(default_settings)

    assert check.status == "ok"


def test_check_abs_api_error(default_settings: Settings):
    default_settings.abs_base_url = "http://abs:13378"
    default_settings.abs_api_token = "token"
    default_settings.abs_library_id = "lib-001"
    with patch(
        "app.diagnostics.AudiobookshelfClient.check_connectivity",
        return_value=ScanResult(success=False, error="Authentication failed (HTTP 401)"),
    ):
        check = check_abs_api(default_settings)

    assert check.status == "error"


def test_diagnostic_groups_cover_all_checks():
    checks = [
        DiagnosticCheck("ytdlp", "yt-dlp", "ok", "Available"),
        DiagnosticCheck("ffmpeg", "ffmpeg", "ok", "Available"),
        DiagnosticCheck("ffprobe", "ffprobe", "ok", "Available"),
        DiagnosticCheck("redis", "Redis", "ok", "Connected"),
        DiagnosticCheck("database", "Database", "ok", "Writable"),
        DiagnosticCheck("output_root", "Output root", "ok", "Writable"),
        DiagnosticCheck("work_dir", "Work directory", "ok", "Writable"),
        DiagnosticCheck("cookies", "Cookies file", "warn", "Not configured"),
        DiagnosticCheck("abs_api", "Audiobookshelf API", "skipped", "Not configured"),
    ]
    groups = diagnostic_groups(checks)
    grouped_ids = {check.id for group in groups for check in group.checks}
    assert grouped_ids == {check.id for check in checks}


@patch("app.routes.diagnostics.run_diagnostics")
def test_diagnostics_page_returns_checks(mock_run: MagicMock, client: TestClient):
    mock_run.return_value = [
        DiagnosticCheck("ytdlp", "yt-dlp", "ok", "Available", detail="2024.10.07"),
        DiagnosticCheck("ffmpeg", "ffmpeg", "ok", "Available", detail="ffmpeg version 7.0"),
        DiagnosticCheck("ffprobe", "ffprobe", "ok", "Available", detail="ffprobe version 7.0"),
        DiagnosticCheck("redis", "Redis", "ok", "Connected"),
        DiagnosticCheck("database", "Database", "ok", "Writable", path="/data/app.db"),
        DiagnosticCheck("output_root", "Output root", "ok", "Writable"),
        DiagnosticCheck("work_dir", "Work directory", "ok", "Writable"),
        DiagnosticCheck("cookies", "Cookies file", "warn", "Not configured"),
        DiagnosticCheck("abs_api", "Audiobookshelf API", "skipped", "Not configured"),
    ]

    response = client.get("/diagnostics")
    assert response.status_code == 200
    assert "Diagnostics" in response.text
    assert "yt-dlp" in response.text
    assert "Audiobookshelf API" in response.text


@patch("app.routes.diagnostics.run_diagnostics")
def test_api_diagnostics_returns_json(mock_run: MagicMock, client: TestClient):
    mock_run.return_value = [
        DiagnosticCheck("ytdlp", "yt-dlp", "ok", "Available", detail="2024.10.07"),
    ]

    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"][0]["id"] == "ytdlp"
    assert body["checks"][0]["status"] == "ok"
