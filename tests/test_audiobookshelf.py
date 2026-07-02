"""Tests for Audiobookshelf API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
from app.config import Settings
from app.services.audiobookshelf import AudiobookshelfClient


def make_client(
    base_url: str = "",
    api_token: str = "",
    library_id: str = "",
) -> AudiobookshelfClient:
    import os

    os.environ.setdefault("APP_SECRET_KEY", "test")
    os.environ["ABS_BASE_URL"] = base_url
    os.environ["ABS_API_TOKEN"] = api_token
    os.environ["ABS_LIBRARY_ID"] = library_id
    s = Settings()
    return AudiobookshelfClient(s)


# ── Not configured ─────────────────────────────────────────────────────────────


def test_scan_skipped_when_not_configured():
    client = make_client()  # no ABS config
    result = client.trigger_scan()
    assert result.skipped is True
    assert result.success is False


def test_scan_skipped_missing_library_id():
    client = make_client(base_url="http://abs:13378", api_token="token")
    result = client.trigger_scan()
    assert result.skipped is True


# ── Successful scan ────────────────────────────────────────────────────────────


def test_scan_success():
    client = make_client(
        base_url="http://abs:13378",
        api_token="secret-token",
        library_id="lib-001",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200

    with patch("app.services.audiobookshelf.httpx.post", return_value=mock_response) as mock_post:
        result = client.trigger_scan()

    assert result.success is True
    assert result.skipped is False
    assert result.error is None

    # Verify the correct URL was called
    args, _kwargs = mock_post.call_args
    assert "lib-001" in args[0]
    assert "http://abs:13378" in args[0]


def test_scan_token_not_in_url():
    """API token must not appear in the request URL."""
    client = make_client(
        base_url="http://abs:13378",
        api_token="super-secret-token",
        library_id="lib-001",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.services.audiobookshelf.httpx.post", return_value=mock_response) as mock_post:
        client.trigger_scan()

    args, _kwargs = mock_post.call_args
    url = args[0]
    assert "super-secret-token" not in url


def test_scan_http_error():
    client = make_client(
        base_url="http://abs:13378",
        api_token="token",
        library_id="lib-001",
    )
    mock_response = MagicMock()
    mock_response.status_code = 401
    http_error = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)
    mock_response.raise_for_status.side_effect = http_error

    with patch("app.services.audiobookshelf.httpx.post", return_value=mock_response):
        result = client.trigger_scan()

    assert result.success is False
    assert result.skipped is False
    assert "401" in result.error  # type: ignore[operator]


def test_scan_connection_error():
    client = make_client(
        base_url="http://abs:13378",
        api_token="token",
        library_id="lib-001",
    )
    with patch(
        "app.services.audiobookshelf.httpx.post",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        result = client.trigger_scan()

    assert result.success is False
    assert result.error is not None
    assert "ConnectError" in result.error or "connection" in result.error.lower()


# ── Overriding library_id ─────────────────────────────────────────────────────


def test_scan_with_explicit_library_id():
    client = make_client(
        base_url="http://abs:13378",
        api_token="token",
        library_id="default-lib",
    )
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    with patch("app.services.audiobookshelf.httpx.post", return_value=mock_response) as mock_post:
        client.trigger_scan(library_id="override-lib")

    args, _ = mock_post.call_args
    assert "override-lib" in args[0]
    assert "default-lib" not in args[0]
