"""ImportPipeline service: encapsulates the multi-stage download and conversion pipeline."""

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Job, JobStatus
from app.services.audiobookshelf import AudiobookshelfClient
from app.services.ffmpeg import FfmpegProgress, FfmpegService
from app.services.filesystem import FilesystemService
from app.services.jobs import sync_get_job, sync_record_attempt, sync_update_job
from app.services.ytdlp import YtDlpService, parse_ytdlp_progress_line

logger = logging.getLogger(__name__)


@dataclass
class DownloadArtifact:
    path: Path
    format: str | None = None
    filesize: int | None = None
    title: str | None = None
    uploader: str | None = None
    chapter_count: int | None = None


@dataclass
class ConversionArtifact:
    path: Path
    used_fallback: bool
    verified: bool = False
    codec_name: str | None = None
    duration_seconds: float | None = None
    chapter_count: int | None = None
    filesize: int | None = None


class PipelineCancelledError(Exception):
    """Raised when the pipeline is cancelled by the user."""

    pass


class PipelineFailedError(Exception):
    """Raised when a pipeline stage fails."""

    pass


class ImportPipeline:
    """Synchronously orchestrates a job's import pipeline stages."""

    # ── Progress ranges ─────────────────────────────────────────────────────
    _RANGE_SETUP = (0.0, 2.0)
    _RANGE_DOWNLOAD = (2.0, 70.0)
    _RANGE_CONVERT = (72.0, 90.0)
    # Milestones
    _M_DOWNLOAD_DONE = 70.0
    _M_LOCATING = 72.0
    _M_PREPARE_CONVERT = 72.0
    _M_CONVERT_DONE = 90.0
    _M_VERIFY = 92.0
    _M_VERIFIED = 94.0
    _M_SCAN = 96.0
    _M_CLEANUP = 98.0
    _M_CLEANUP_DONE = 99.0
    _M_COMPLETE = 100.0

    _THROTTLE_INTERVAL = 1.0  # seconds between DB writes during streaming phases

    def __init__(self, db: Session, settings: Settings, job_id: str) -> None:
        self.db = db
        self.settings = settings
        self.job_id = job_id
        self._last_progress = -1.0
        self._last_progress_write_time = 0.0
        self._progress_throttle_interval = self._THROTTLE_INTERVAL

    # ── Progress helpers ───────────────────────────────────────────────────

    @staticmethod
    def _map_range(value: float, start: float, end: float) -> float:
        """Map *value* (0.0 to 1.0) into [start, end] and clamp to 0-100."""
        result = start + value * (end - start)
        return max(0.0, min(100.0, result))

    def _set_progress(
        self,
        job: Job,
        *,
        percent: float | None = None,
        label: str | None = None,
        eta: str | None = None,
        speed: str | None = None,
        force: bool = False,
    ) -> None:
        """Persist progress fields, throttled unless *force* is True."""
        now = time.time()
        pct_changed = percent is not None and round(percent) != round(job.progress_percent or 0)
        label_changed = label is not None and label != job.progress_label
        time_passed = now - self._last_progress_write_time > self._THROTTLE_INTERVAL

        if not force and not pct_changed and not label_changed and not time_passed:
            return

        kwargs: dict[str, Any] = {}
        if percent is not None:
            clamped = max(0.0, min(100.0, percent))
            kwargs["progress"] = round(clamped)
            kwargs["progress_percent"] = clamped
        if label is not None:
            kwargs["progress_label"] = label
        if eta is not None:
            kwargs["progress_eta"] = eta
        if speed is not None:
            kwargs["progress_speed"] = speed

        if kwargs:
            sync_update_job(self.db, job, **kwargs)
            self.db.commit()
            self._last_progress_write_time = now
            if percent is not None:
                self._last_progress = percent

    # ── Main entry point ───────────────────────────────────────────────────

    def run(self) -> None:
        """Execute the import pipeline."""
        started_at = datetime.now(tz=UTC)
        job = sync_get_job(self.db, self.job_id)
        if job is None:
            logger.error("Job %s not found in database", self.job_id)
            return

        # Initialize optional artifact variables to build metadata on completion/failure
        dl_artifact: DownloadArtifact | None = None
        conv_artifact: ConversionArtifact | None = None

        # ── Setup ─────────────────────────────────────────────────────────────
        fs = FilesystemService(self.settings)
        log_path = fs.log_path(self.job_id)
        work_dir = fs.ensure_work_dir(self.job_id)

        # Increment attempts and update initial status
        job.attempts = (job.attempts or 0) + 1
        sync_update_job(
            self.db,
            job,
            status=JobStatus.running,
            phase="resolving_output",
            log_file_path=str(log_path),
            work_dir=str(work_dir),
        )
        self.db.commit()
        self._set_progress(job, percent=0.0, label="Setup", eta="", speed="", force=True)

        log_fh = log_path.open("a", encoding="utf-8")

        def log(msg: str) -> None:
            log_fh.write(msg + "\n")
            log_fh.flush()
            logger.info("[%s] %s", self.job_id, msg)

        def check_cancelled() -> bool:
            self.db.commit()
            self.db.refresh(job)
            return job.status == JobStatus.cancelled

        try:
            log(f"=== Job {self.job_id} started at {started_at.isoformat()} ===")
            log(f"[setup] Output root: {self.settings.output_root}")
            log(f"[setup] Work directory: {work_dir}")

            ytdlp_svc = YtDlpService(self.settings)
            ffmpeg_svc = FfmpegService(self.settings)
            abs_client = AudiobookshelfClient(self.settings)

            # ── Resolve output path ────────────────────────────────────────────
            dest_folder = job.destination_folder or ""
            output_title = job.output_title or job.source_title or "Unknown"
            video_id = job.video_id or "unknown"

            try:
                output_path = fs.resolve_output_path(
                    dest_folder, output_title, video_id, job.collision_mode
                )
            except ValueError as exc:
                raise PipelineFailedError(f"Invalid output path: {exc}") from exc

            log(f"[setup] Final output path: {output_path}")
            log(f"URL: {job.url}")
            log(f"DRY_RUN: {self.settings.dry_run}")

            self._set_progress(job, percent=2.0, label="Setup complete", eta="", speed="")

            # ── DRY RUN Mode ──────────────────────────────────────────────────
            if self.settings.dry_run:
                log("--- DRY RUN: building commands only ---")
                dl_template = ytdlp_svc.get_output_template(self.job_id)
                dl_cmd = ytdlp_svc.build_download_command(
                    job.url,
                    self.job_id,
                    dl_template,
                    embed_metadata=job.embed_metadata,
                    embed_thumbnail=job.embed_thumbnail,
                    embed_chapters=job.embed_chapters,
                )
                log(f"[download] yt-dlp command: {' '.join(dl_cmd)}")

                fake_m4a = work_dir / "fake_download.m4a"
                cmd_p = ffmpeg_svc.build_remux_command(fake_m4a, output_path)
                cmd_f = ffmpeg_svc.build_remux_command_fallback(fake_m4a, output_path)
                log(f"[convert] ffmpeg primary: {' '.join(cmd_p)}")
                log(f"[convert] ffmpeg fallback: {' '.join(cmd_f)}")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"DRY RUN fake .m4b content")
                log(f"DRY RUN: created fake output file at {output_path}")

                if check_cancelled():
                    raise PipelineCancelledError()

                self._set_progress(
                    job,
                    percent=self._M_COMPLETE,
                    label="Complete",
                    eta="",
                    speed="",
                    force=True,
                )
                sync_update_job(
                    self.db,
                    job,
                    status=JobStatus.succeeded,
                    phase="succeeded",
                    final_output_path=str(output_path),
                )
                self.db.commit()
                sync_record_attempt(
                    self.db,
                    job,
                    status="succeeded",
                    started_at=started_at,
                    finished_at=datetime.now(tz=UTC),
                )
                self.db.commit()
                log(f"=== Job {self.job_id} completed successfully ===")
                return

            if check_cancelled():
                raise PipelineCancelledError()

            # ── Download ──────────────────────────────────────────────────────
            sync_update_job(
                self.db,
                job,
                status=JobStatus.downloading,
                phase="downloading",
            )
            self.db.commit()
            self._set_progress(
                job,
                percent=self._RANGE_DOWNLOAD[0],
                label="Downloading",
                eta="",
                speed="",
            )
            log("[download] Starting yt-dlp")

            dl_template = ytdlp_svc.get_output_template(self.job_id)
            dl_cmd = ytdlp_svc.build_download_command(
                job.url,
                self.job_id,
                dl_template,
                embed_metadata=job.embed_metadata,
                embed_thumbnail=job.embed_thumbnail,
                embed_chapters=job.embed_chapters,
            )

            # Ensure archive parent dir exists
            if self.settings.archive_file:
                self.settings.archive_file.parent.mkdir(parents=True, exist_ok=True)

            dl_success = self._run_subprocess(
                dl_cmd, log, check_cancelled, is_download=True, job=job
            )
            if not dl_success:
                if check_cancelled():
                    raise PipelineCancelledError()
                raise PipelineFailedError("yt-dlp download failed")

            if check_cancelled():
                raise PipelineCancelledError()

            self._set_progress(
                job,
                percent=self._M_DOWNLOAD_DONE,
                label="Download complete",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(self.db, job, phase="download_complete")
            self.db.commit()

            # ── Locate Artifact ────────────────────────────────────────────────
            self._set_progress(
                job,
                percent=self._M_LOCATING,
                label="Locating downloaded audio",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(
                self.db,
                job,
                status=JobStatus.postprocessing,
                phase="locating_artifact",
            )
            self.db.commit()

            downloaded_file = ytdlp_svc.find_downloaded_file(self.job_id)
            if downloaded_file is None:
                # Check download archive message
                log_content = ""
                if log_path.exists():
                    log_content = log_path.read_text(encoding="utf-8", errors="replace")

                if "has already been recorded in the archive" in log_content:
                    err_msg = (
                        "Video has already been recorded in the download archive. "
                        "To re-download, remove the video ID from your youtube-archive.txt file."
                    )
                else:
                    err_msg = "Could not locate downloaded audio file in work directory"
                raise PipelineFailedError(err_msg)

            # Wrap in DownloadArtifact
            dl_artifact = DownloadArtifact(
                path=downloaded_file,
                format=self.settings.ytdlp_audio_format,
                filesize=downloaded_file.stat().st_size,
                title=job.source_title,
                uploader=job.uploader,
                chapter_count=job.chapter_count,
            )

            log(f"[download] Completed: {dl_artifact.path}")
            log(f"[download] Artifact: format={dl_artifact.format} size={dl_artifact.filesize}")

            self._set_progress(
                job,
                percent=self._M_LOCATING,
                label="Download artifact ready",
                eta="",
                speed="",
                force=True,
            )

            if check_cancelled():
                raise PipelineCancelledError()

            # ── Remux to .m4b ─────────────────────────────────────────────────
            self._set_progress(
                job,
                percent=self._M_PREPARE_CONVERT,
                label="Preparing conversion",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(
                self.db,
                job,
                status=JobStatus.converting,
                phase="converting",
            )
            self.db.commit()
            log("[convert] Starting ffmpeg remux")
            log(f"[convert] Input: {dl_artifact.path}")
            log(f"[convert] Output: {output_path}")

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Determine media duration for conversion progress mapping
            media_duration: float | None = float(job.duration) if job.duration is not None else None

            # Build progress callback for ffmpeg
            def _on_ffmpeg_progress(fp: FfmpegProgress) -> None:
                if (
                    media_duration is not None
                    and media_duration > 0
                    and fp.out_time_seconds is not None
                ):
                    ratio = min(fp.out_time_seconds / media_duration, 1.0)
                    overall = self._map_range(ratio, *self._RANGE_CONVERT)
                    label = (
                        "Retrying conversion without cover art"
                        if fp.raw.get("_fallback")
                        else "Converting to M4B"
                    )
                    self._set_progress(
                        job,
                        percent=overall,
                        label=label,
                        speed=fp.speed,
                    )
                else:
                    self._set_progress(
                        job,
                        percent=75.0,
                        label="Converting to M4B",
                        speed=fp.speed,
                    )

            # Wrap on_progress to inject fallback flag
            _in_fallback = False

            def _on_ffmpeg_progress_primary(fp: FfmpegProgress) -> None:
                _on_ffmpeg_progress(fp)

            def _on_ffmpeg_progress_fallback(fp: FfmpegProgress) -> None:
                fp.raw["_fallback"] = "1"
                _on_ffmpeg_progress(fp)

            remux_result = ffmpeg_svc.run_remux(
                dl_artifact.path,
                output_path,
                log_fh,
                check_cancelled=check_cancelled,
                on_progress=_on_ffmpeg_progress,
            )

            if not remux_result.success:
                if check_cancelled():
                    raise PipelineCancelledError()
                raise PipelineFailedError(f"ffmpeg remux failed: {remux_result.error}")

            self._set_progress(
                job,
                percent=self._M_CONVERT_DONE,
                label="Conversion complete",
                eta="",
                speed="",
                force=True,
            )

            # Wrap in ConversionArtifact
            conv_artifact = ConversionArtifact(
                path=output_path,
                used_fallback=remux_result.used_fallback,
                filesize=output_path.stat().st_size if output_path.exists() else None,
            )

            log(f"[convert] Completed: {conv_artifact.path}")
            log(f"[convert] Used fallback: {str(conv_artifact.used_fallback).lower()}")

            if check_cancelled():
                raise PipelineCancelledError()

            sync_update_job(self.db, job, phase="conversion_complete")
            self.db.commit()

            # ── Verify ────────────────────────────────────────────────────────
            self._set_progress(
                job,
                percent=self._M_VERIFY,
                label="Verifying output",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(
                self.db,
                job,
                status=JobStatus.verifying,
                phase="verifying",
            )
            self.db.commit()
            log("[verify] Running ffprobe")

            try:
                probe = ffmpeg_svc.verify_output(conv_artifact.path)
                conv_artifact.verified = True
                conv_artifact.codec_name = probe.codec_name
                conv_artifact.duration_seconds = probe.duration_seconds
                conv_artifact.chapter_count = probe.chapter_count
                conv_artifact.filesize = probe.file_size

                log(f"[verify] Audio codec: {conv_artifact.codec_name}")
                log(f"[verify] Duration: {conv_artifact.duration_seconds}s")
                log(f"[verify] Chapters: {conv_artifact.chapter_count}")
                log(f"[verify] File size: {conv_artifact.filesize} bytes")

                self._set_progress(
                    job,
                    percent=self._M_VERIFIED,
                    label="Output verified",
                    eta="",
                    speed="",
                    force=True,
                )
                sync_update_job(
                    self.db,
                    job,
                    chapter_count=conv_artifact.chapter_count,
                    phase="verified",
                )
                self.db.commit()
            except (FileNotFoundError, RuntimeError) as exc:
                self._set_progress(
                    job,
                    percent=self._M_VERIFY,
                    label="Verification failed",
                    eta="",
                    speed="",
                    force=True,
                )
                raise PipelineFailedError(f"Output verification failed: {exc}") from exc

            if check_cancelled():
                raise PipelineCancelledError()

            # ── Audiobookshelf Scan ───────────────────────────────────────────
            if job.trigger_abs_scan and self.settings.abs_scan_after_success:
                self._set_progress(
                    job,
                    percent=self._M_SCAN,
                    label="Triggering Audiobookshelf scan",
                    eta="",
                    speed="",
                    force=True,
                )
                sync_update_job(
                    self.db,
                    job,
                    status=JobStatus.scanning,
                    phase="scanning",
                )
                self.db.commit()
                log("[scan] Triggering Audiobookshelf scan")
                scan_result = abs_client.trigger_scan()
                if scan_result.skipped:
                    log("[scan] ABS scan skipped (not configured)")
                    self._set_progress(
                        job,
                        percent=self._M_SCAN,
                        label="Audiobookshelf scan skipped",
                        eta="",
                        speed="",
                        force=True,
                    )
                elif scan_result.success:
                    log("[scan] ABS scan triggered successfully")
                    self._set_progress(
                        job,
                        percent=self._M_SCAN,
                        label="Audiobookshelf scan triggered",
                        eta="",
                        speed="",
                        force=True,
                    )
                else:
                    log(f"[scan] ABS scan failed (non-fatal): {scan_result.error}")
                    self._set_progress(
                        job,
                        percent=self._M_SCAN,
                        label="Audiobookshelf scan failed",
                        eta="",
                        speed="",
                        force=True,
                    )

            if check_cancelled():
                raise PipelineCancelledError()

            # ── Cleanup ───────────────────────────────────────────────────────
            self._set_progress(
                job,
                percent=self._M_CLEANUP,
                label="Cleaning up temporary files",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(self.db, job, phase="cleanup")
            self.db.commit()
            if self.settings.cleanup_temp_on_success:
                log("[cleanup] Cleaning up work directory")
                fs.cleanup_work_dir(self.job_id)

            self._set_progress(
                job,
                percent=self._M_CLEANUP_DONE,
                label="Cleanup complete",
                eta="",
                speed="",
                force=True,
            )

            # ── Success ───────────────────────────────────────────────────────
            self._set_progress(
                job,
                percent=self._M_COMPLETE,
                label="Complete",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(
                self.db,
                job,
                status=JobStatus.succeeded,
                phase="succeeded",
                final_output_path=str(output_path),
            )
            self.db.commit()
            sync_record_attempt(
                self.db,
                job,
                status="succeeded",
                started_at=started_at,
                finished_at=datetime.now(tz=UTC),
                artifact_metadata=self._build_metadata_json(dl_artifact, conv_artifact),
            )
            self.db.commit()

            log(f"=== Job {self.job_id} completed successfully ===")
            log(f"Output: {output_path}")

        except PipelineCancelledError:
            log("Job execution halted due to cancellation.")
            self._set_progress(
                job,
                label="Cancelled",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(
                self.db,
                job,
                status=JobStatus.cancelled,
                phase="cancelled",
            )
            self.db.commit()
            sync_record_attempt(
                self.db,
                job,
                status="cancelled",
                started_at=started_at,
                finished_at=datetime.now(tz=UTC),
                artifact_metadata=self._build_metadata_json(dl_artifact, conv_artifact),
            )
            self.db.commit()
            if self.settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(self.job_id)

        except Exception as exc:
            err_msg = str(exc)
            log(f"FAILED: {err_msg}")
            self._set_progress(
                job,
                label="Failed",
                eta="",
                speed="",
                force=True,
            )
            sync_update_job(
                self.db,
                job,
                status=JobStatus.failed,
                phase="failed",
                error_message=err_msg,
            )
            self.db.commit()
            sync_record_attempt(
                self.db,
                job,
                status="failed",
                error_message=err_msg,
                started_at=started_at,
                finished_at=datetime.now(tz=UTC),
                artifact_metadata=self._build_metadata_json(dl_artifact, conv_artifact),
            )
            self.db.commit()
            if self.settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(self.job_id)

        finally:
            with contextlib.suppress(Exception):
                log_fh.close()

    def _run_subprocess(
        self,
        cmd: list[str],
        log_func: Callable[[str], None],
        check_cancelled: Callable[[], bool],
        is_download: bool = False,
        job: Job | None = None,
    ) -> bool:
        """Run a subprocess, stream stdout to log, parse progress, check cancellation."""
        from app.services.process_runner import run_streaming_process

        def on_line(line: str) -> None:
            if is_download and job:
                progress_info = parse_ytdlp_progress_line(line)
                if progress_info and progress_info.percent is not None:
                    dl_pct = progress_info.percent
                    # Map download percent (0-100) into overall job range (2-70%)
                    ratio = dl_pct / 100.0
                    overall = self._map_range(ratio, *self._RANGE_DOWNLOAD)
                    pct_int = round(overall)
                    now = time.time()

                    prog_changed = pct_int != round(self._last_progress)
                    eta_changed = progress_info.eta != (job.progress_eta or "")
                    speed_changed = progress_info.speed != (job.progress_speed or "")
                    time_passed = now - self._last_progress_write_time > self._THROTTLE_INTERVAL

                    if prog_changed or eta_changed or speed_changed or time_passed:
                        sync_update_job(
                            self.db,
                            job,
                            progress=pct_int,
                            progress_percent=round(overall, 1),
                            progress_eta=progress_info.eta,
                            progress_speed=progress_info.speed,
                            progress_label="Downloading",
                        )
                        self.db.commit()
                        self._last_progress = overall
                        self._last_progress_write_time = now

        res = run_streaming_process(
            cmd,
            log_line=log_func,
            check_cancelled=check_cancelled,
            on_line=on_line,
        )

        return res.returncode == 0 and not res.cancelled

    def _build_metadata_json(
        self,
        dl_artifact: DownloadArtifact | None,
        conv_artifact: ConversionArtifact | None,
    ) -> str | None:
        """Serialize DownloadArtifact and ConversionArtifact to a compact JSON string."""
        data: dict[str, Any] = {}
        if dl_artifact:
            data["download"] = {
                "path": str(dl_artifact.path),
                "format": dl_artifact.format,
                "filesize": dl_artifact.filesize,
            }
        if conv_artifact:
            data["conversion"] = {
                "path": str(conv_artifact.path),
                "used_fallback": conv_artifact.used_fallback,
                "codec_name": conv_artifact.codec_name,
                "duration_seconds": conv_artifact.duration_seconds,
                "chapter_count": conv_artifact.chapter_count,
                "filesize": conv_artifact.filesize,
            }
        if not data:
            return None
        return json.dumps(data)
