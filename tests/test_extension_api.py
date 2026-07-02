"""Tests for browser extension API endpoints."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from app.main import create_app
from app.services.ytdlp import YtDlpService
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Use an isolated SQLite DB per test and clear cached engines."""
    db_path = tmp_path / "test-extension-api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    import app.db as db_module

    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create a test client for the FastAPI app."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def extension_enabled_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create a test client with extension API enabled."""
    monkeypatch.setenv("EXTENSION_API_ENABLED", "true")
    monkeypatch.setenv("EXTENSION_API_TOKEN", "test-token-12345")
    # Need to clear the settings cache after setting env vars
    import app.config as cfg_module

    cfg_module._settings = None
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def extension_enabled_no_token_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Create a test client with extension API enabled but no token."""
    monkeypatch.setenv("EXTENSION_API_ENABLED", "true")
    monkeypatch.setenv("EXTENSION_API_TOKEN", "")
    import app.config as cfg_module

    cfg_module._settings = None
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def mocked_ytdlp(monkeypatch):
    """Mock YtDlpService methods for tests."""

    mock_svc = Mock(spec=YtDlpService)
    mock_svc.validate_url.return_value = Mock(valid=True)
    mock_svc.run_preview.return_value = Mock(
        id="test123",
        title="Test Video",
        uploader="Test Uploader",
        uploader_id="user123",
        channel="Test Channel",
        channel_id="channel123",
        duration=180,
        upload_date="20240101",
        thumbnail="https://example.com/thumb.jpg",
        chapter_count=3,
        webpage_url="https://youtube.com/watch?v=test123",
    )

    # app.main imports YtDlpService by name, so patch the binding in app.main
    # (and in app.services.ytdlp for any code that resolves it from there).
    def _factory(*args, **kwargs):
        return mock_svc

    monkeypatch.setattr("app.main.YtDlpService", _factory)
    monkeypatch.setattr("app.services.ytdlp.YtDlpService", _factory)
    yield mock_svc


@pytest.fixture
def mocked_queue(monkeypatch):
    """Mock enqueue_job_task and update_job_status for tests."""
    with monkeypatch.context() as m:

        async def _noop(*a, **kw):
            return None

        # app.main imports these by name, so patch the bindings in app.main
        m.setattr("app.main.enqueue_job_task", lambda job_id: "rq-job-123")
        m.setattr("app.main.update_job_status", _noop)
        yield m


# ---------------------------------------------------------------------------
# Extension Status Endpoint Tests
# ---------------------------------------------------------------------------


def test_extension_status_disabled_by_default(client):
    """Test that extension API returns 404 when disabled."""
    response = client.get("/api/extension/status")
    assert response.status_code == 404
    assert "Extension API not enabled" in response.text


def test_extension_status_enabled_no_token(extension_enabled_no_token_client):
    """Test extension status when enabled but no token required."""
    response = extension_enabled_no_token_client.get("/api/extension/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["extension_api_enabled"] is True
    assert data["auth_required"] is False
    assert data["app"] == "yt-abs-importer"


def test_extension_status_enabled_with_token(extension_enabled_client):
    """Test extension status when enabled and token required."""
    response = extension_enabled_client.get("/api/extension/status")
    assert response.status_code == 401


def test_extension_status_with_bearer_token(extension_enabled_client):
    """Test extension status with Bearer token."""
    response = extension_enabled_client.get(
        "/api/extension/status",
        headers={"Authorization": "Bearer test-token-12345"},
    )
    assert response.status_code == 200


def test_extension_status_with_wrong_token(extension_enabled_client):
    """Test extension status with wrong token rejects access."""
    response = extension_enabled_client.get(
        "/api/extension/status",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    assert "Invalid extension API token" in response.text


def test_extension_status_with_xtabs_token(extension_enabled_client):
    """Test extension status with X-YTABS-Token header."""
    response = extension_enabled_client.get(
        "/api/extension/status",
        headers={"X-YTABS-Token": "test-token-12345"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Extension Queue Endpoint Tests
# ---------------------------------------------------------------------------


def test_extension_queue_disabled_by_default(client):
    """Test extension queue returns 404 when API is disabled."""
    response = client.post(
        "/api/extension/queue",
        json={
            "url": "https://www.youtube.com/watch?v=test123",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 404


def test_extension_queue_enabled_no_token(
    extension_enabled_no_token_client, mocked_ytdlp, mocked_queue
):
    """Test extension queue when enabled but no token required."""
    response = extension_enabled_no_token_client.post(
        "/api/extension/queue",
        json={
            "url": "https://www.youtube.com/watch?v=test123",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert "rq_job_id" in data
    assert data["status"] == "queued"
    assert data["title"] == "Test Video"


def test_extension_queue_enabled_with_token(extension_enabled_client, mocked_ytdlp, mocked_queue):
    """Test extension queue with valid bearer token."""
    response = extension_enabled_client.post(
        "/api/extension/queue",
        headers={"Authorization": "Bearer test-token-12345"},
        json={
            "url": "https://www.youtube.com/watch?v=test123",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert "rq_job_id" in data
    assert data["status"] == "queued"


def test_extension_queue_with_xtabs_token(extension_enabled_client, mocked_ytdlp, mocked_queue):
    """Test extension queue with X-YTABS-Token header."""
    response = extension_enabled_client.post(
        "/api/extension/queue",
        headers={"X-YTABS-Token": "test-token-12345"},
        json={
            "url": "https://www.youtube.com/watch?v=test123",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert "rq_job_id" in data


def test_extension_queue_wrong_token(extension_enabled_client, mocked_ytdlp, mocked_queue):
    """Test extension queue with wrong token is rejected."""
    response = extension_enabled_client.post(
        "/api/extension/queue",
        headers={"Authorization": "Bearer wrong-token"},
        json={
            "url": "https://www.youtube.com/watch?v=test123",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 401
    assert "Invalid extension API token" in response.text


def test_extension_queue_invalid_url(extension_enabled_no_token_client, mocked_ytdlp, mocked_queue):
    """Test extension queue with invalid URL returns 400."""
    from app.services.ytdlp import UrlValidationResult

    mocked_ytdlp.validate_url.return_value = UrlValidationResult(valid=False, error="URL is empty")

    response = extension_enabled_no_token_client.post(
        "/api/extension/queue",
        json={
            "url": "https://example.com/not-youtube",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 400
    assert "URL is empty" in response.text


def test_extension_queue_metadata_failure(
    extension_enabled_no_token_client, mocked_ytdlp, mocked_queue
):
    """Test extension queue when metadata fetch fails returns 422."""
    mocked_ytdlp.run_preview.side_effect = Exception("yt-dlp failed")

    response = extension_enabled_no_token_client.post(
        "/api/extension/queue",
        json={
            "url": "https://www.youtube.com/watch?v=test123",
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 422
    assert "yt-dlp failed" in response.text


def test_extension_queue_json_parsing_error(
    extension_enabled_no_token_client, mocked_ytdlp, mocked_queue
):
    """Test extension queue with invalid JSON returns 400."""
    response = extension_enabled_no_token_client.post(
        "/api/extension/queue",
        headers={"Content-Type": "application/json"},
        data="invalid json",
    )
    assert response.status_code == 400
    assert "Invalid JSON body" in response.text


def test_extension_queue_no_url_field(
    extension_enabled_no_token_client, mocked_ytdlp, mocked_queue
):
    """Test extension queue without URL field returns 400."""
    response = extension_enabled_no_token_client.post(
        "/api/extension/queue",
        json={
            "destination_folder": "",
            "output_title": "",
            "embed_metadata": True,
            "embed_thumbnail": True,
            "embed_chapters": True,
            "trigger_abs_scan": False,
        },
    )
    assert response.status_code == 400
    assert "URL is required" in response.text


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_extension_api_disabled_in_settings(extension_enabled_no_token_client):
    """Test that extension API disabled setting is reflected in status."""
    # The fixture sets EXTENSION_API_ENABLED=true, so we need to test with default
    import app.config as cfg_module

    cfg_module._settings = None

    if "EXTENSION_API_ENABLED" in os.environ:
        del os.environ["EXTENSION_API_ENABLED"]

    client = TestClient(create_app())
    response = client.get("/api/extension/status")
    assert response.status_code == 404
    assert "Extension API not enabled" in response.text
