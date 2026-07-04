"""Tests for playlist/channel flat-playlist enumeration."""

from __future__ import annotations

import pytest
from app.services.ytdlp import (
    PlaylistEntry,
    PlaylistMetadata,
    YtDlpService,
    is_channel_url,
    is_playlist_url,
)


def make_svc(**kwargs) -> YtDlpService:
    import os

    os.environ.setdefault("APP_SECRET_KEY", "test")
    for key, value in kwargs.items():
        os.environ[key] = str(value)
    from app.config import Settings

    return YtDlpService(Settings())


def test_build_flat_playlist_command_shape():
    svc = make_svc()
    cmd = svc.build_flat_playlist_command(
        "https://www.youtube.com/playlist?list=PL123",
        limit=100,
    )
    assert cmd[0] == "yt-dlp"
    assert "--skip-download" in cmd
    assert "--flat-playlist" in cmd
    assert "--dump-single-json" in cmd
    assert "--playlist-end" in cmd
    end_idx = cmd.index("--playlist-end")
    assert cmd[end_idx + 1] == "101"
    assert "--no-playlist" not in cmd
    assert "https://www.youtube.com/playlist?list=PL123" in cmd
    assert isinstance(cmd, list)
    assert all(isinstance(part, str) for part in cmd)


def test_build_flat_playlist_command_fetches_one_extra_for_truncation():
    svc = make_svc()
    cmd = svc.build_flat_playlist_command("https://www.youtube.com/@channel", limit=5)
    end_idx = cmd.index("--playlist-end")
    assert cmd[end_idx + 1] == "6"


def test_playlist_entry_from_json_builds_watch_url():
    entry = PlaylistEntry.from_json({"id": "abc123", "title": "Talk", "duration": 120})
    assert entry is not None
    assert entry.id == "abc123"
    assert entry.title == "Talk"
    assert entry.url == "https://www.youtube.com/watch?v=abc123"
    assert entry.duration == 120


def test_playlist_entry_from_json_uses_webpage_url():
    entry = PlaylistEntry.from_json(
        {
            "id": "abc123",
            "title": "Talk",
            "webpage_url": "https://www.youtube.com/watch?v=abc123&t=1",
        }
    )
    assert entry is not None
    assert entry.url == "https://www.youtube.com/watch?v=abc123&t=1"


def test_playlist_entry_from_json_skips_missing_id():
    assert PlaylistEntry.from_json({"title": "No id"}) is None


def test_playlist_metadata_from_json_playlist_shape():
    data = {
        "id": "PL123",
        "title": "My Playlist",
        "webpage_url": "https://www.youtube.com/playlist?list=PL123",
        "uploader": "Host",
        "entries": [
            {"id": "v1", "title": "One", "duration": 10},
            {"id": "v2", "title": "Two", "duration": 20},
        ],
    }
    meta = PlaylistMetadata.from_json(data, source_type="playlist", limit=100)
    assert meta.id == "PL123"
    assert meta.title == "My Playlist"
    assert meta.source_type == "playlist"
    assert meta.entry_count == 2
    assert meta.truncated is False
    assert meta.entries[0].id == "v1"
    assert meta.entries[1].url.endswith("v2")


def test_playlist_metadata_from_json_channel_shape():
    data = {
        "id": "UCxxxx",
        "channel": "Cool Channel",
        "channel_id": "UCxxxx",
        "entries": [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
            {"id": "c", "title": "C"},
        ],
    }
    meta = PlaylistMetadata.from_json(data, source_type="channel", limit=2)
    assert meta.source_type == "channel"
    assert meta.title == "Cool Channel"
    assert meta.entry_count == 2
    assert meta.truncated is True
    assert [e.id for e in meta.entries] == ["a", "b"]


def test_playlist_metadata_truncation_false_when_at_limit():
    data = {
        "id": "PL1",
        "title": "Exact",
        "entries": [{"id": f"v{i}", "title": f"V{i}"} for i in range(3)],
    }
    meta = PlaylistMetadata.from_json(data, source_type="playlist", limit=3)
    assert meta.entry_count == 3
    assert meta.truncated is False


def test_is_playlist_and_channel_url_helpers():
    assert is_playlist_url("https://www.youtube.com/playlist?list=PL123")
    assert is_playlist_url("https://www.youtube.com/watch?v=abc&list=PL123")
    assert not is_playlist_url("https://www.youtube.com/watch?v=abc")
    assert is_channel_url("https://www.youtube.com/@someone")
    assert is_channel_url("https://www.youtube.com/channel/UCxxxx")
    assert not is_channel_url("https://www.youtube.com/watch?v=abc")


def test_sanitize_command_url_allows_playlist_shapes_when_policy_disabled():
    """Command sanitization must not re-apply playlist/channel policy flags."""
    svc = make_svc(ALLOW_PLAYLISTS="false", ALLOW_CHANNELS="false")
    playlist = "https://www.youtube.com/playlist?list=PL123"
    channel = "https://www.youtube.com/@someone"
    assert svc._sanitize_command_url(playlist) == playlist
    assert svc._sanitize_command_url(channel) == channel


def test_sanitize_command_url_rejects_unsafe_inputs():
    svc = make_svc()
    with pytest.raises(ValueError, match="control characters"):
        svc._sanitize_command_url("https://www.youtube.com/watch?v=abc\n--evil")
    with pytest.raises(ValueError, match="allowlist"):
        svc._sanitize_command_url("https://evil.example/watch?v=abc")
    with pytest.raises(ValueError, match="http"):
        svc._sanitize_command_url("ftp://www.youtube.com/watch?v=abc")
