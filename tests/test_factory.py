"""Tests for application factory startup behaviour."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.factory import (
    _fallback_ui_version,
    _fetch_latest_ui_version_async,
    _resolve_ui_version,
    create_app,
)
from app.routes.pages import templates
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "test-factory.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.delenv("ABS_MEDIA_IMPORTER_UI_VERSION", raising=False)

    import app.config as cfg_module
    import app.db as db_module

    cfg_module._settings = None
    db_module._async_engine = None
    db_module._async_session_factory = None
    db_module._sync_engine = None
    db_module._sync_session_factory = None


def test_resolve_ui_version_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ABS_MEDIA_IMPORTER_UI_VERSION", "v9.9.9")
    assert _resolve_ui_version("1.2.3") == "v9.9.9"


def test_resolve_ui_version_falls_back_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ABS_MEDIA_IMPORTER_UI_VERSION", raising=False)
    with patch("app.factory.httpx.AsyncClient") as mock_client:
        assert _resolve_ui_version("1.2.3") == "v1.2.3"
        mock_client.assert_not_called()


def test_fallback_ui_version_preserves_v_prefix() -> None:
    assert _fallback_ui_version("v1.0.0") == "v1.0.0"
    assert _fallback_ui_version("1.0.0") == "v1.0.0"


@pytest.mark.asyncio
async def test_fetch_latest_ui_version_returns_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABS_MEDIA_IMPORTER_GITHUB_REPO", "owner/repo")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"tag_name": "v2.0.0"}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("app.factory.httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_latest_ui_version_async("v1.0.0")

    assert result == "v2.0.0"
    mock_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_latest_ui_version_returns_fallback_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABS_MEDIA_IMPORTER_GITHUB_REPO", "owner/repo")

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("app.factory.httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_latest_ui_version_async("v1.0.0")

    assert result == "v1.0.0"


@pytest.mark.asyncio
async def test_fetch_latest_ui_version_skips_invalid_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABS_MEDIA_IMPORTER_GITHUB_REPO", "not-a-repo")
    with patch("app.factory.httpx.AsyncClient") as mock_client:
        result = await _fetch_latest_ui_version_async("v1.0.0")
    assert result == "v1.0.0"
    mock_client.assert_not_called()


def test_startup_does_not_block_on_slow_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """App must become ready even when the GitHub release lookup is slow."""
    monkeypatch.delenv("ABS_MEDIA_IMPORTER_UI_VERSION", raising=False)

    async def _slow_fetch(fallback: str) -> str:
        await asyncio.sleep(2.0)
        return "v99.0.0"

    with patch("app.factory._fetch_latest_ui_version_async", side_effect=_slow_fetch):
        started = time.monotonic()
        with TestClient(create_app()) as client:
            elapsed = time.monotonic() - started
            # Startup must not wait for the 2s background fetch.
            assert elapsed < 1.0
            response = client.get("/health")
            assert response.status_code == 200
            # Fallback is applied immediately; background task may still be running.
            assert client.app.state.ui_version.startswith("v")


def test_env_override_skips_background_github_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABS_MEDIA_IMPORTER_UI_VERSION", "v8.8.8")

    with (
        patch(
            "app.factory._fetch_latest_ui_version_async",
            new_callable=AsyncMock,
        ) as mock_fetch,
        TestClient(create_app()) as client,
    ):
        assert client.app.state.ui_version == "v8.8.8"
        assert client.app.state.ui_version_task is None
        assert templates.env.globals["app_ui_version"] == "v8.8.8"
        mock_fetch.assert_not_called()


def test_background_fetch_updates_ui_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ABS_MEDIA_IMPORTER_UI_VERSION", raising=False)

    async def _fast_fetch(fallback: str) -> str:
        return "v3.3.3"

    with (
        patch("app.factory._fetch_latest_ui_version_async", side_effect=_fast_fetch),
        TestClient(create_app()) as client,
    ):
        task = client.app.state.ui_version_task
        assert task is not None
        # Wait for the background task to finish.
        deadline = time.monotonic() + 2.0
        while not task.done() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert task.done()
        assert client.app.state.ui_version == "v3.3.3"
        assert templates.env.globals["app_ui_version"] == "v3.3.3"
