"""Tests for YouTube URL validation."""

from __future__ import annotations

import pytest
from app.config import Settings
from app.services.ytdlp import YtDlpService


def make_svc(allow_playlists: bool = False, allow_channels: bool = False) -> YtDlpService:
    import os

    os.environ.setdefault("APP_SECRET_KEY", "test")
    os.environ["ALLOW_PLAYLISTS"] = str(allow_playlists).lower()
    os.environ["ALLOW_CHANNELS"] = str(allow_channels).lower()
    s = Settings()
    return YtDlpService(s)


# ── Valid URLs ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=CcYToxtmFHs",
        "https://youtube.com/watch?v=CcYToxtmFHs",
        "https://m.youtube.com/watch?v=CcYToxtmFHs",
        "https://music.youtube.com/watch?v=CcYToxtmFHs",
        "https://youtu.be/CcYToxtmFHs",
        "https://youtu.be/CcYToxtmFHs?si=some_tracking_param",
    ],
)
def test_valid_single_video_urls(url: str):
    svc = make_svc()
    result = svc.validate_url(url)
    assert result.valid, f"Expected valid for {url}: {result.error}"


# ── Invalid: empty / bad scheme ───────────────────────────────────────────────


def test_empty_url():
    result = make_svc().validate_url("")
    assert not result.valid
    assert "empty" in result.error.lower()  # type: ignore[union-attr]


def test_non_http_scheme():
    result = make_svc().validate_url("ftp://youtube.com/watch?v=abc")
    assert not result.valid


# ── Invalid: non-allowlist domain ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/123456",
        "https://dailymotion.com/video/x1",
        "https://evil.com/watch?v=xyz",
        "https://youtube.evil.com/watch?v=xyz",
    ],
)
def test_non_allowlist_domains(url: str):
    result = make_svc().validate_url(url)
    assert not result.valid
    assert "allowlist" in result.error.lower()  # type: ignore[union-attr]


# ── Playlist rejection ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/playlist?list=PL12345",
        "https://www.youtube.com/watch?v=abc&list=PL12345",
        "https://youtube.com/watch?v=abc&list=WL",
    ],
)
def test_playlist_url_rejected_by_default(url: str):
    svc = make_svc(allow_playlists=False)
    result = svc.validate_url(url)
    assert not result.valid
    assert "playlist" in result.error.lower()  # type: ignore[union-attr]


def test_playlist_url_allowed_when_configured():
    svc = make_svc(allow_playlists=True)
    result = svc.validate_url("https://www.youtube.com/playlist?list=PL12345")
    assert result.valid


# ── Channel rejection ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/channel/UCxxxxxx",
        "https://www.youtube.com/@pintswithaquinas",
        "https://www.youtube.com/c/ChannelName",
        "https://www.youtube.com/user/OldStyle",
    ],
)
def test_channel_url_rejected_by_default(url: str):
    svc = make_svc(allow_channels=False)
    result = svc.validate_url(url)
    assert not result.valid
    assert "channel" in result.error.lower()  # type: ignore[union-attr]


def test_channel_url_allowed_when_configured():
    svc = make_svc(allow_channels=True)
    result = svc.validate_url("https://www.youtube.com/@pintswithaquinas")
    assert result.valid
