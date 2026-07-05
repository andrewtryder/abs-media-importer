"""Tests for yt-dlp command construction."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.services.ytdlp import VideoMetadata, YtDlpService


def make_svc(**kwargs) -> YtDlpService:  # type: ignore[return]
    import os

    os.environ.setdefault("APP_SECRET_KEY", "test")
    for k, v in kwargs.items():
        os.environ[k] = str(v)
    s = Settings()
    return YtDlpService(s)


# ── Preview command ────────────────────────────────────────────────────────────


def test_preview_command_structure():
    svc = make_svc()
    cmd = svc.build_preview_command("https://youtu.be/abc123")
    assert cmd[0] == "yt-dlp"
    assert "--skip-download" in cmd
    assert "--dump-json" in cmd
    assert "--no-playlist" in cmd
    assert "https://youtu.be/abc123" in cmd


# ── Download command ────────────────────────────────────────────────────────────


def test_download_command_contains_no_playlist():
    svc = make_svc()
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/data/work/job-1/download/%(title)s.%(ext)s",
    )
    assert "--no-playlist" in cmd


def test_single_video_commands_keep_no_playlist_flag():
    """Single-video preview/download always pass --no-playlist.

    Playlist/channel batch imports use a separate flat-playlist command path.
    """
    svc = make_svc(ALLOW_PLAYLISTS="true", ALLOW_CHANNELS="true")
    preview_cmd = svc.build_preview_command("https://youtu.be/abc123")
    download_cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/data/work/job-1/download/%(title)s.%(ext)s",
    )
    assert "--no-playlist" in preview_cmd
    assert "--no-playlist" in download_cmd


def test_allow_playlist_channel_settings_describe_batch_import():
    """Registry help text describes selection-based batch import."""
    from app.settings_registry import SETTINGS_BY_KEY

    playlists = SETTINGS_BY_KEY["allow_playlists"]
    channels = SETTINGS_BY_KEY["allow_channels"]

    assert playlists.label == "Allow Playlist URLs"
    assert channels.label == "Allow Channel URLs"
    for spec in (playlists, channels):
        assert "not yet supported" not in spec.help_text
        assert "batch" in spec.help_text.lower()


def test_download_command_audio_format():
    svc = make_svc(YTDLP_AUDIO_FORMAT="m4a")
    cmd = svc.build_download_command(
        "https://youtu.be/abc123", "job-1", "/tmp/out/%(title)s.%(ext)s"
    )
    assert "--audio-format" in cmd
    idx = cmd.index("--audio-format")
    assert cmd[idx + 1] == "m4a"


def test_download_command_embed_flags_default():
    svc = make_svc()
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/tmp/out/%(title)s.%(ext)s",
        embed_metadata=True,
        embed_thumbnail=True,
        embed_chapters=True,
    )
    assert "--embed-metadata" in cmd
    assert "--embed-thumbnail" in cmd
    assert "--embed-chapters" in cmd


def test_download_command_embed_flags_off():
    svc = make_svc()
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/tmp/out/%(title)s.%(ext)s",
        embed_metadata=False,
        embed_thumbnail=False,
        embed_chapters=False,
    )
    assert "--embed-metadata" not in cmd
    assert "--embed-thumbnail" not in cmd
    assert "--embed-chapters" not in cmd


def test_download_command_archive(tmp_path: Path):
    archive = tmp_path / "archive.txt"
    svc = make_svc(ARCHIVE_FILE=str(archive))
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/tmp/out/%(title)s.%(ext)s",
        use_archive=True,
    )
    assert "--download-archive" in cmd
    idx = cmd.index("--download-archive")
    assert cmd[idx + 1] == str(archive)


def test_download_command_skip_archive():
    svc = make_svc()
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/tmp/out/%(title)s.%(ext)s",
        use_archive=False,
    )
    assert "--download-archive" not in cmd


def test_download_command_extra_args():
    svc = make_svc(YTDLP_EXTRA_ARGS="--verbose --no-warnings")
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/tmp/out/%(title)s.%(ext)s",
        use_archive=False,
    )
    assert "--verbose" in cmd
    assert "--no-warnings" in cmd


def test_download_command_url_at_end():
    svc = make_svc()
    cmd = svc.build_download_command(
        "https://youtu.be/abc123",
        "job-1",
        "/tmp/out/%(title)s.%(ext)s",
        use_archive=False,
    )
    assert cmd[-1] == "https://youtu.be/abc123"
    # Separator '--' should precede the URL
    assert cmd[-2] == "--"


def test_custom_ytdlp_bin():
    svc = make_svc(YTDLP_BIN="/usr/local/bin/yt-dlp")
    cmd = svc.build_preview_command("https://youtu.be/abc123")
    assert cmd[0] == "/usr/local/bin/yt-dlp"


# ── VideoMetadata.from_json ───────────────────────────────────────────────────


def test_video_metadata_from_json():
    data = {
        "id": "CcYToxtmFHs",
        "title": "Test Video",
        "uploader": "Test Channel",
        "uploader_id": "@testchannel",
        "channel": "Test Channel",
        "channel_id": "UCtest",
        "duration": 3600,
        "upload_date": "20240101",
        "thumbnail": "https://img.youtube.com/test.jpg",
        "chapters": [{"title": "Intro", "start_time": 0.0}],
        "webpage_url": "https://youtu.be/CcYToxtmFHs",
    }
    meta = VideoMetadata.from_json(data)
    assert meta.id == "CcYToxtmFHs"
    assert meta.title == "Test Video"
    assert meta.chapter_count == 1
    assert meta.duration == 3600


def test_video_metadata_missing_optional_fields():
    data = {"id": "abc", "title": "Minimal"}
    meta = VideoMetadata.from_json(data)
    assert meta.uploader is None
    assert meta.chapter_count == 0
    assert meta.duration is None


# ── find_downloaded_file ──────────────────────────────────────────────────────


def test_find_downloaded_file(tmp_path: Path):
    svc = make_svc(WORK_DIR=str(tmp_path))
    download_dir = tmp_path / "job-1" / "download" / "@channel"
    download_dir.mkdir(parents=True)
    expected = download_dir / "My Video.m4a"
    expected.write_bytes(b"audio")
    found = svc.find_downloaded_file("job-1")
    assert found == expected


def test_find_downloaded_file_not_found(tmp_path: Path):
    svc = make_svc(WORK_DIR=str(tmp_path))
    assert svc.find_downloaded_file("job-xyz") is None


# ── progress parsing ─────────────────────────────────────────────────────────


def test_parse_ytdlp_progress_line():
    from app.services.ytdlp import parse_ytdlp_progress_line

    # Happy path: typical line with all fields
    line = "[download]  12.3% of 48.55MiB at 3.21MiB/s ETA 00:13"
    res = parse_ytdlp_progress_line(line)
    assert res is not None
    assert res.percent == 12.3
    assert res.total == "48.55MiB"
    assert res.speed == "3.21MiB/s"
    assert res.eta == "00:13"
    assert res.raw_line == line

    # Happy path: completed download line
    line = "[download] 100% of 48.55MiB in 00:15"
    res = parse_ytdlp_progress_line(line)
    assert res is not None
    assert res.percent == 100.0
    assert res.total == "48.55MiB"
    assert res.speed is None
    assert res.eta == "00:15"

    # Unrelated line: starts with [download] but is not progress
    line = "[download] Destination: /tmp/hello.m4a"
    assert parse_ytdlp_progress_line(line) is None

    # Unrelated line: completely different
    line = "[youtube] CcYToxtmFHs: Downloading webpage"
    assert parse_ytdlp_progress_line(line) is None

    # Partial/malformed progress line (should not raise)
    line = "[download]  abc% of 48.55MiB"
    assert parse_ytdlp_progress_line(line) is None

    line = "[download]  50% of unknown at fast speed"
    res = parse_ytdlp_progress_line(line)
    assert res is not None
    assert res.percent == 50.0
    assert res.total is None
    assert res.speed is None
    assert res.eta is None
