"""ffmpeg service: remux .m4a → .m4b and verify output."""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FfprobeResult:
    file_size: int
    has_audio: bool
    chapter_count: int
    duration_seconds: float | None
    codec_name: str | None


@dataclass
class RemuxResult:
    success: bool
    used_fallback: bool
    error: str | None = None


@dataclass
class FfmpegProgress:
    """Parsed ffmpeg progress from -progress pipe:1 output."""

    out_time_ms: int | None = None
    out_time_seconds: float | None = None
    speed: str | None = None
    progress: str | None = None
    raw: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> FfmpegProgress:
        out_time_seconds: float | None = None
        out_time_ms: int | None = None

        raw_out_time_ms = data.get("out_time_ms")
        if raw_out_time_ms is not None:
            try:
                ms_val = int(raw_out_time_ms)
                out_time_ms = ms_val
                out_time_seconds = ms_val / 1_000_000.0
            except (ValueError, TypeError):
                pass

        if out_time_seconds is None:
            raw_out_time_us = data.get("out_time_us")
            if raw_out_time_us is not None:
                try:
                    us_val = int(raw_out_time_us)
                    out_time_seconds = us_val / 1_000_000.0
                except (ValueError, TypeError):
                    pass

        if out_time_seconds is None:
            raw_out_time = data.get("out_time")
            if raw_out_time is not None:
                try:
                    parts = raw_out_time.split(":")
                    if len(parts) == 3:
                        h, m, s = parts
                        out_time_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                except (ValueError, TypeError):
                    pass

        return cls(
            out_time_ms=out_time_ms,
            out_time_seconds=out_time_seconds,
            speed=data.get("speed"),
            progress=data.get("progress"),
            raw=dict(data),
        )


class FfmpegProgressParser:
    """Stateful parser for ffmpeg -progress pipe:1 output.

    ffmpeg emits groups of key=value lines ending with progress=continue
    or progress=end.  This parser collects those groups and returns a
    FfmpegProgress when a group is complete.
    """

    def __init__(self) -> None:
        self._current: dict[str, str] = {}

    def feed_line(self, line: str) -> FfmpegProgress | None:
        """Feed a single line of ffmpeg output.  Returns a FfmpegProgress
        when a progress group completes, or None."""
        line = line.strip()
        if "=" not in line:
            return None

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        self._current[key] = value

        if key == "progress" and value in ("continue", "end"):
            result = FfmpegProgress.from_dict(self._current)
            self._current = {}
            return result

        return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FfmpegService:
    """Wrapper around ffmpeg/ffprobe subprocess calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── Command builders ──────────────────────────────────────────────────────

    def build_remux_command(
        self,
        input_path: Path,
        output_path: Path,
        *,
        progress: bool = False,
    ) -> list[str]:
        """
        Primary remux command.

        Maps audio stream + optional video stream (cover art).
        Uses -f ipod which is the correct container for .m4b/.m4a.

        If *progress* is True, includes -progress pipe:1 -stats_period 1 -nostats
        so the caller can parse structured ffmpeg progress output.
        """
        s = self.settings
        cmd = [
            s.ffmpeg_bin,
            "-y",
        ]
        if progress:
            cmd += ["-progress", "pipe:1", "-stats_period", "1", "-nostats"]
        cmd += [
            "-i",
            str(input_path),
            "-map",
            "0:a:0",  # first audio stream
            "-map",
            "0:v?",  # optional video stream (cover art), skip if absent
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c",
            "copy",
            "-disposition:v:0",
            "attached_pic",
            "-f",
            "ipod",
        ]
        cmd.extend(s.ffmpeg_extra_args)
        cmd.append(str(output_path))
        return cmd

    def build_remux_command_fallback(
        self,
        input_path: Path,
        output_path: Path,
        *,
        progress: bool = False,
    ) -> list[str]:
        """
        Fallback remux command: audio-only, no cover art.

        Used when the primary command fails due to incompatible video/data
        streams (e.g. 'Tag text incompatible with output codec id').
        """
        s = self.settings
        cmd = [
            s.ffmpeg_bin,
            "-y",
        ]
        if progress:
            cmd += ["-progress", "pipe:1", "-stats_period", "1", "-nostats"]
        cmd += [
            "-i",
            str(input_path),
            "-map",
            "0:a:0",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c",
            "copy",
            "-f",
            "ipod",
        ]
        cmd.extend(s.ffmpeg_extra_args)
        cmd.append(str(output_path))
        return cmd

    def build_ffprobe_command(self, path: Path) -> list[str]:
        """Build ffprobe command to inspect output file."""
        return [
            self.settings.ffprobe_bin,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_chapters",
            "-show_format",
            str(path),
        ]

    # ── Execution ─────────────────────────────────────────────────────────────

    def run_remux(
        self,
        input_path: Path,
        output_path: Path,
        log_fh: object | None = None,
        check_cancelled: Callable[[], bool] | None = None,
        on_progress: Callable[[FfmpegProgress], None] | None = None,
    ) -> RemuxResult:
        """
        Attempt primary remux; fall back to audio-only on failure.

        Args:
            input_path: Source .m4a file.
            output_path: Destination .m4b path.
            log_fh: Open file handle to write ffmpeg output into (optional).
            check_cancelled: Callback to check if job is cancelled.
            on_progress: Optional callback receiving FfmpegProgress updates.

        Returns:
            RemuxResult indicating success and whether fallback was used.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Primary attempt
        cmd = self.build_remux_command(input_path, output_path, progress=on_progress is not None)
        logger.debug("ffmpeg primary: %s", cmd)
        success, err = self._run_cmd(
            cmd, log_fh, check_cancelled=check_cancelled, on_progress=on_progress
        )

        if success:
            return RemuxResult(success=True, used_fallback=False)

        if check_cancelled and check_cancelled():
            return RemuxResult(success=False, used_fallback=False, error="Cancelled by user")

        # Log the primary failure
        _write_log(log_fh, f"\n[ffmpeg] Primary command failed: {err}\n")
        _write_log(log_fh, "[ffmpeg] Retrying without cover art stream...\n")
        logger.warning("ffmpeg primary failed, trying fallback: %s", err)

        # Remove partial output
        if output_path.exists():
            output_path.unlink()

        # Fallback attempt
        cmd_fallback = self.build_remux_command_fallback(
            input_path, output_path, progress=on_progress is not None
        )
        logger.debug("ffmpeg fallback: %s", cmd_fallback)
        success_fb, err_fb = self._run_cmd(
            cmd_fallback, log_fh, check_cancelled=check_cancelled, on_progress=on_progress
        )

        if success_fb:
            return RemuxResult(success=True, used_fallback=True)

        return RemuxResult(success=False, used_fallback=True, error=err_fb)

    def verify_output(self, output_path: Path) -> FfprobeResult:
        """
        Run ffprobe on *output_path* and return inspection result.

        Raises FileNotFoundError if output doesn't exist.
        Raises RuntimeError if ffprobe fails or no audio stream found.
        """
        if not output_path.exists():
            raise FileNotFoundError(f"Output file not found: {output_path}")

        if output_path.stat().st_size == 0:
            raise RuntimeError("Output file is empty (0 bytes)")

        cmd = self.build_ffprobe_command(output_path)
        logger.debug("ffprobe: %s", cmd)

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"ffprobe returned invalid JSON: {exc}") from exc

        streams = data.get("streams", [])
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        if not audio_streams:
            raise RuntimeError("No audio stream found in output file")

        chapters = data.get("chapters", [])
        fmt = data.get("format", {})
        duration_str = fmt.get("duration")
        duration = float(duration_str) if duration_str else None
        codec = audio_streams[0].get("codec_name") if audio_streams else None

        return FfprobeResult(
            file_size=output_path.stat().st_size,
            has_audio=True,
            chapter_count=len(chapters),
            duration_seconds=duration,
            codec_name=codec,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_cmd(
        self,
        cmd: list[str],
        log_fh: object | None,
        check_cancelled: Callable[[], bool] | None = None,
        on_progress: Callable[[FfmpegProgress], None] | None = None,
    ) -> tuple[bool, str | None]:
        """
        Run *cmd* via process_runner, streaming stdout/stderr in real-time to *log_fh*.

        Returns (success, error_message).
        """
        from app.services.process_runner import run_streaming_process

        error_lines = []
        parser = FfmpegProgressParser() if on_progress else None

        def log_line(line: str) -> None:
            _write_log(log_fh, line + "\n")
            error_lines.append(line + "\n")
            if len(error_lines) > 50:
                error_lines.pop(0)

        def on_line(line: str) -> None:
            if parser is not None and on_progress is not None:
                progress = parser.feed_line(line)
                if progress is not None:
                    on_progress(progress)

        res = run_streaming_process(
            cmd,
            log_line=log_line,
            check_cancelled=check_cancelled,
            on_line=on_line,
        )

        if res.cancelled:
            return False, "Cancelled by user"

        if res.returncode == 0:
            return True, None

        err_msg = "".join(error_lines)
        return False, f"ffmpeg exited {res.returncode}: {err_msg[-500:]}"


def _write_log(fh: object | None, text: str) -> None:
    if fh is not None:
        with contextlib.suppress(Exception):
            fh.write(text)  # type: ignore[attr-defined]
            fh.flush()  # type: ignore[attr-defined]
