"""Tests for ffmpeg command construction and remux logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.config import Settings
from app.services.ffmpeg import FfmpegService


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


def test_primary_command_no_shell_true(tmp_path: Path):
    svc = make_svc()
    cmd = svc.build_remux_command(tmp_path / "a.m4a", tmp_path / "b.m4b")
    assert isinstance(cmd, list)
    assert all(isinstance(c, str) for c in cmd)


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


def test_fallback_command_no_shell_true(tmp_path: Path):
    cmd = make_svc().build_remux_command_fallback(tmp_path / "a.m4a", tmp_path / "b.m4b")
    assert isinstance(cmd, list)


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
