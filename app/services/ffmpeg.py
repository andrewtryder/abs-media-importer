"""ffmpeg service: remux .m4a → .m4b and verify output."""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FfmpegService:
    """Wrapper around ffmpeg/ffprobe subprocess calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── Command builders ──────────────────────────────────────────────────────

    def build_remux_command(self, input_path: Path, output_path: Path) -> list[str]:
        """
        Primary remux command.

        Maps audio stream + optional video stream (cover art).
        Uses -f ipod which is the correct container for .m4b/.m4a.
        """
        s = self.settings
        cmd = [
            s.ffmpeg_bin,
            "-y",
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

    def build_remux_command_fallback(self, input_path: Path, output_path: Path) -> list[str]:
        """
        Fallback remux command: audio-only, no cover art.

        Used when the primary command fails due to incompatible video/data
        streams (e.g. 'Tag text incompatible with output codec id').
        """
        s = self.settings
        cmd = [
            s.ffmpeg_bin,
            "-y",
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
    ) -> RemuxResult:
        """
        Attempt primary remux; fall back to audio-only on failure.

        Args:
            input_path: Source .m4a file.
            output_path: Destination .m4b path.
            log_fh: Open file handle to write ffmpeg output into (optional).
            check_cancelled: Callback to check if job is cancelled.

        Returns:
            RemuxResult indicating success and whether fallback was used.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Primary attempt
        cmd = self.build_remux_command(input_path, output_path)
        logger.debug("ffmpeg primary: %s", cmd)
        success, err = self._run_cmd(cmd, log_fh, check_cancelled=check_cancelled)

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
        cmd_fallback = self.build_remux_command_fallback(input_path, output_path)
        logger.debug("ffmpeg fallback: %s", cmd_fallback)
        success_fb, err_fb = self._run_cmd(cmd_fallback, log_fh, check_cancelled=check_cancelled)

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
    ) -> tuple[bool, str | None]:
        """
        Run *cmd* via subprocess, streaming stdout/stderr in real-time to *log_fh*.

        Returns (success, error_message).
        """
        _write_log(log_fh, f"$ {' '.join(cmd)}\n")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            return False, f"Binary not found: {exc}"

        import time

        last_check = time.time()

        error_lines = []
        assert proc.stdout is not None
        # NOTE: Reading from stdout is blocking. If the subprocess does not output
        # anything or takes a long time, the cancellation check will be delayed
        # until the next line is read. This is a known limitation.
        for line in proc.stdout:
            _write_log(log_fh, line)
            error_lines.append(line)
            if len(error_lines) > 50:
                error_lines.pop(0)

            if check_cancelled and time.time() - last_check > 3.0:
                last_check = time.time()
                if check_cancelled():
                    _write_log(
                        log_fh, "\n[ffmpeg] Cancellation requested. Terminating subprocess...\n"
                    )
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    _write_log(log_fh, "[ffmpeg] Subprocess terminated.\n")
                    return False, "Cancelled by user"

        proc.wait()
        if proc.returncode == 0:
            return True, None

        err_msg = "".join(error_lines)
        return False, f"ffmpeg exited {proc.returncode}: {err_msg[-500:]}"


def _write_log(fh: object | None, text: str) -> None:
    if fh is not None:
        with contextlib.suppress(Exception):
            fh.write(text)  # type: ignore[attr-defined]
            fh.flush()  # type: ignore[attr-defined]
