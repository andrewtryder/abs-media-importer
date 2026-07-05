"""Tests for ffmpeg command construction and remux logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.config import Settings
from app.services.ffmpeg import FfmpegProgress, FfmpegProgressParser, FfmpegService


def make_svc(**kwargs) -> FfmpegService:  # type: ignore[return]
    import os

    os.environ.setdefault("APP_SECRET_KEY", "test")
    for k, v in kwargs.items():
        os.environ[k] = str(v)
    s = Settings()
    return FfmpegService(s)


# ── Primary remux command ──────────────────────────────────────────────────────


def test_primary_command_structure(tmp_path: Path):
    svc = make_svc()
    input_f = tmp_path / "audio.m4a"
    output_f = tmp_path / "audio.m4b"
    cmd = svc.build_remux_command(input_f, output_f)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "-i" in cmd
    assert "-map" in cmd
    assert "0:a:0" in cmd
    assert "0:v?" in cmd
    assert "-map_metadata" in cmd
    assert "-map_chapters" in cmd
    assert "-c" in cmd and "copy" in cmd
    assert "-disposition:v:0" in cmd and "attached_pic" in cmd
    assert "-f" in cmd and "ipod" in cmd
    assert str(output_f) == cmd[-1]


# ── Fallback command ──────────────────────────────────────────────────────────


def test_fallback_command_no_video_map(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command_fallback(tmp_path / "a.m4a", tmp_path / "b.m4b")
    assert "0:v?" not in cmd
    assert "attached_pic" not in cmd
    assert "0:a:0" in cmd
    assert "-map_metadata" in cmd
    assert "-map_chapters" in cmd
    assert "ipod" in cmd


# ── Extra args ────────────────────────────────────────────────────────────────


def test_ffmpeg_extra_args_included(tmp_path: Path):
    svc = make_svc(FFMPEG_EXTRA_ARGS="-loglevel verbose")
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b")
    assert "-loglevel" in cmd
    assert "verbose" in cmd


# ── Custom binary path ─────────────────────────────────────────────────────────


def test_custom_ffmpeg_bin(tmp_path: Path):
    svc = make_svc(FFMPEG_BIN="/usr/local/bin/ffmpeg")
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b")
    assert cmd[0] == "/usr/local/bin/ffmpeg"


# ── run_remux: success on primary ─────────────────────────────────────────────


def test_run_remux_primary_success(tmp_path: Path):
    svc = make_svc()
    input_f = tmp_path / "input.m4a"
    input_f.write_bytes(b"fake m4a")
    output_f = tmp_path / "output.m4b"

    mock_proc = MagicMock()
    mock_proc.stdout = ["ffmpeg line 1\n", "ffmpeg line 2\n"]
    mock_proc.returncode = 0
    mock_proc.wait = MagicMock()

    with patch("app.services.ffmpeg.subprocess.Popen", return_value=mock_proc):
        result = svc.run_remux(input_f, output_f)

    assert result.success is True
    assert result.used_fallback is False


# ── run_remux: fallback triggered ─────────────────────────────────────────────


def test_run_remux_falls_back_on_primary_failure(tmp_path: Path):
    svc = make_svc()
    input_f = tmp_path / "input.m4a"
    input_f.write_bytes(b"fake m4a")
    output_f = tmp_path / "output.m4b"

    fail_proc = MagicMock()
    fail_proc.stdout = ["Tag text incompatible with output codec id\n"]
    fail_proc.returncode = 1
    fail_proc.wait = MagicMock()

    ok_proc = MagicMock()
    ok_proc.stdout = ["fallback success\n"]
    ok_proc.returncode = 0
    ok_proc.wait = MagicMock()

    with patch("app.services.ffmpeg.subprocess.Popen", side_effect=[fail_proc, ok_proc]):
        result = svc.run_remux(input_f, output_f)

    assert result.success is True
    assert result.used_fallback is True


def test_run_remux_both_fail(tmp_path: Path):
    svc = make_svc()
    input_f = tmp_path / "input.m4a"
    input_f.write_bytes(b"fake m4a")
    output_f = tmp_path / "output.m4b"

    fail_proc1 = MagicMock()
    fail_proc1.stdout = ["primary failed\n"]
    fail_proc1.returncode = 1
    fail_proc1.wait = MagicMock()

    fail_proc2 = MagicMock()
    fail_proc2.stdout = ["fallback failed\n"]
    fail_proc2.returncode = 1
    fail_proc2.wait = MagicMock()

    with patch("app.services.ffmpeg.subprocess.Popen", side_effect=[fail_proc1, fail_proc2]):
        result = svc.run_remux(input_f, output_f)

    assert result.success is False
    assert result.used_fallback is True


# ── verify_output ─────────────────────────────────────────────────────────────


def test_verify_output_missing_file(tmp_path: Path):
    svc = make_svc()
    with pytest.raises(FileNotFoundError):
        svc.verify_output(tmp_path / "nonexistent.m4b")


def test_verify_output_empty_file(tmp_path: Path):
    svc = make_svc()
    empty = tmp_path / "empty.m4b"
    empty.write_bytes(b"")
    with pytest.raises(RuntimeError, match="empty"):
        svc.verify_output(empty)


def test_verify_output_no_audio_stream(tmp_path: Path):
    svc = make_svc()
    f = tmp_path / "output.m4b"
    f.write_bytes(b"fake")

    probe_json = json.dumps({"streams": [], "chapters": [], "format": {}})
    mock_result = MagicMock()
    mock_result.stdout = probe_json
    mock_result.returncode = 0

    with (
        patch("app.services.ffmpeg.subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="No audio stream"),
    ):
        svc.verify_output(f)


def test_verify_output_success(tmp_path: Path):
    svc = make_svc()
    f = tmp_path / "output.m4b"
    f.write_bytes(b"fake audio data" * 100)

    probe_json = json.dumps(
        {
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
            "chapters": [{"id": 0}, {"id": 1}],
            "format": {"duration": "3600.0"},
        }
    )
    mock_result = MagicMock()
    mock_result.stdout = probe_json
    mock_result.returncode = 0

    with patch("app.services.ffmpeg.subprocess.run", return_value=mock_result):
        result = svc.verify_output(f)

    assert result.has_audio is True
    assert result.chapter_count == 2
    assert result.duration_seconds == 3600.0
    assert result.codec_name == "aac"


# ── Progress flag in command builders ───────────────────────────────────────


def test_primary_command_with_progress_flag(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b", progress=True)
    assert "-progress" in cmd
    assert "pipe:1" in cmd
    assert "-stats_period" in cmd
    assert "-nostats" in cmd
    # -y should come before -progress
    y_idx = cmd.index("-y")
    prog_idx = cmd.index("-progress")
    assert prog_idx > y_idx


def test_primary_command_without_progress_flag(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b", progress=False)
    assert "-progress" not in cmd
    assert "-stats_period" not in cmd
    assert "-nostats" not in cmd


def test_fallback_command_with_progress_flag(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command_fallback(tmp_path / "a.m4a", tmp_path / "b.m4b", progress=True)
    assert "-progress" in cmd
    assert "pipe:1" in cmd
    assert "-stats_period" in cmd
    assert "-nostats" in cmd


def test_fallback_command_without_progress_flag(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command_fallback(tmp_path / "a.m4a", tmp_path / "b.m4b", progress=False)
    assert "-progress" not in cmd


# ── FFmpeg progress parsing ────────────────────────────────────────────────


def test_ffmpeg_progress_from_dict_out_time_ms():
    data = {"out_time_ms": "12345678", "speed": "12.3x", "progress": "continue"}
    fp = FfmpegProgress.from_dict(data)
    assert fp.out_time_ms == 12345678
    assert fp.out_time_seconds == pytest.approx(12.345678)
    assert fp.speed == "12.3x"
    assert fp.progress == "continue"


def test_ffmpeg_progress_from_dict_out_time_us():
    data = {"out_time_us": "12345678", "speed": "3.2x", "progress": "end"}
    fp = FfmpegProgress.from_dict(data)
    assert fp.out_time_seconds == pytest.approx(12.345678)
    assert fp.speed == "3.2x"
    assert fp.progress == "end"


def test_ffmpeg_progress_from_dict_out_time_timestamp():
    data = {"out_time": "00:01:02.500000", "speed": "3.2x", "progress": "end"}
    fp = FfmpegProgress.from_dict(data)
    assert fp.out_time_seconds == pytest.approx(62.5)
    assert fp.speed == "3.2x"
    assert fp.progress == "end"


def test_ffmpeg_progress_from_dict_missing_time():
    data = {"speed": "1.0x", "progress": "continue"}
    fp = FfmpegProgress.from_dict(data)
    assert fp.out_time_ms is None
    assert fp.out_time_seconds is None
    assert fp.speed == "1.0x"
    assert fp.progress == "continue"


def test_ffmpeg_progress_from_dict_empty():
    fp = FfmpegProgress.from_dict({})
    assert fp.out_time_ms is None
    assert fp.out_time_seconds is None
    assert fp.speed is None
    assert fp.progress is None


def test_ffmpeg_progress_parser_full_group():
    """Verify stateful parser returns progress when a group completes."""
    parser = FfmpegProgressParser()
    lines = [
        "frame=1",
        "fps=0.00",
        "out_time_ms=5000000",
        "speed=5.0x",
        "progress=continue",
    ]
    result = None
    for line in lines:
        r = parser.feed_line(line)
        if r is not None:
            result = r

    assert result is not None
    assert result.out_time_seconds == pytest.approx(5.0)
    assert result.speed == "5.0x"
    assert result.progress == "continue"


def test_ffmpeg_progress_parser_ignores_non_kv_lines():
    parser = FfmpegProgressParser()
    assert parser.feed_line("some random log line") is None
    assert parser.feed_line("") is None
    assert parser.feed_line("[libx264 @ 0x1234] using SAR=1/1") is None


def test_ffmpeg_progress_parser_malformed_does_not_raise():
    parser = FfmpegProgressParser()
    # should not raise
    assert parser.feed_line("=value") is None
    assert parser.feed_line("key=") is None


def test_progress_command_insertion_order(tmp_path: Path):
    """Validate -progress flags come after -y but before the file arguments."""
    svc = make_svc()
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b", progress=True)
    # -y is first after the binary
    assert cmd[1] == "-y"
    # -progress must come before -i
    prog_idx = cmd.index("-progress")
    input_idx = cmd.index("-i")
    assert prog_idx < input_idx


def test_primary_command_uses_copy_when_loudness_disabled(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b")
    assert "-c" in cmd and "copy" in cmd
    assert "loudnorm" not in " ".join(cmd)


def test_primary_command_applies_loudnorm_when_enabled(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command(
        tmp_path / "a.m4a",
        tmp_path / "b.m4b",
        loudness_normalize=True,
        loudness_target_lufs="-18",
        audio_bitrate="160k",
    )
    joined = " ".join(cmd)
    assert "loudnorm=I=-18:TP=-1.5:LRA=11" in joined
    assert "-c:a" in cmd and "aac" in cmd
    assert "-b:a" in cmd and "160k" in cmd
    assert "-c:v" in cmd and "copy" in cmd
    assert "-c copy" not in " ".join(cmd)


def test_fallback_command_applies_loudnorm_without_video_copy(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command_fallback(
        tmp_path / "a.m4a",
        tmp_path / "b.m4b",
        loudness_normalize=True,
    )
    joined = " ".join(cmd)
    assert "loudnorm" in joined
    assert "-c:v" not in cmd
    assert "-c:a" in cmd and "aac" in cmd
