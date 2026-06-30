"""RQ worker task: run_import_job.

This module is the entry point for background import jobs.
It is executed by the RQ worker process (not inside FastAPI's event loop).
All I/O is synchronous.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime

from app.config import get_settings
from app.db import get_sync_db
from app.models import Job, JobStatus
from app.services.audiobookshelf import AudiobookshelfClient
from app.services.ffmpeg import FfmpegService
from app.services.filesystem import FilesystemService
from app.services.jobs import sync_get_job, sync_record_attempt, sync_update_job
from app.services.ytdlp import YtDlpService
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


def run_import_job(job_id: str) -> None:
    """
    Execute the full import pipeline for a job.

    Phases:
      running → downloading → postprocessing → converting → verifying
      → scanning → succeeded | failed
    """
    settings = get_settings()
    db = get_sync_db()
    started_at = datetime.now(tz=UTC)

    try:
        job = sync_get_job(db, job_id)
        if job is None:
            logger.error("Job %s not found in database", job_id)
            return

        # ── Setup ─────────────────────────────────────────────────────────────
        fs = FilesystemService(settings)
        log_path = fs.log_path(job_id)
        work_dir = fs.ensure_work_dir(job_id)

        job.attempts = (job.attempts or 0) + 1
        sync_update_job(
            db,
            job,
            status=JobStatus.running,
            phase="running",
            log_file_path=str(log_path),
            work_dir=str(work_dir),
        )
        db.commit()

        log_fh = log_path.open("a", encoding="utf-8")

        def log(msg: str) -> None:
            log_fh.write(msg + "\n")
            log_fh.flush()
            logger.info("[%s] %s", job_id, msg)

        def check_cancelled_cb() -> bool:
            assert job is not None
            db.refresh(job)
            return job.status == JobStatus.cancelled

        log(f"=== Job {job_id} started at {started_at.isoformat()} ===")
        log(f"URL: {job.url}")
        log(f"Output title: {job.output_title}")
        log(f"Destination: {job.destination_folder}")
        log(f"DRY_RUN: {settings.dry_run}")

        ytdlp_svc = YtDlpService(settings)
        ffmpeg_svc = FfmpegService(settings)
        abs_client = AudiobookshelfClient(settings)

        # ── Resolve output path ────────────────────────────────────────────────
        dest_folder = job.destination_folder or ""
        output_title = job.output_title or job.source_title or "Unknown"
        video_id = job.video_id or "unknown"

        try:
            output_path = fs.resolve_output_path(
                dest_folder, output_title, video_id, job.collision_mode
            )
        except ValueError as exc:
            _fail(db, job, log, f"Invalid output path: {exc}", log_fh, started_at)
            return

        log(f"Output path: {output_path}")

        # ── DRY RUN mode ──────────────────────────────────────────────────────
        if settings.dry_run:
            log("--- DRY RUN: building commands only ---")
            dl_template = ytdlp_svc.get_output_template(job_id)
            dl_cmd = ytdlp_svc.build_download_command(
                job.url,
                job_id,
                dl_template,
                embed_metadata=job.embed_metadata,
                embed_thumbnail=job.embed_thumbnail,
                embed_chapters=job.embed_chapters,
            )
            log(f"yt-dlp command: {dl_cmd}")

            fake_m4a = work_dir / "fake_download.m4a"
            log(f"ffmpeg primary: {ffmpeg_svc.build_remux_command(fake_m4a, output_path)}")
            log(
                f"ffmpeg fallback: {ffmpeg_svc.build_remux_command_fallback(fake_m4a, output_path)}"
            )

            # Create a fake output file for UI testing
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"DRY RUN fake .m4b content")
            log(f"DRY RUN: created fake output file at {output_path}")

            if check_cancelled_cb():
                log("Job execution halted due to cancellation.")
                if settings.cleanup_temp_on_failure:
                    fs.cleanup_work_dir(job_id)
                return

            sync_update_job(
                db,
                job,
                status=JobStatus.succeeded,
                phase="succeeded",
                final_output_path=str(output_path),
            )
            db.commit()
            sync_record_attempt(
                db,
                job,
                status="succeeded",
                started_at=started_at,
                finished_at=datetime.now(tz=UTC),
            )
            db.commit()
            log_fh.close()
            return

        if check_cancelled_cb():
            log("Job execution halted due to cancellation.")
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        # ── Download ──────────────────────────────────────────────────────────
        sync_update_job(db, job, status=JobStatus.downloading, phase="downloading")
        db.commit()
        log("Phase: downloading")

        dl_template = ytdlp_svc.get_output_template(job_id)
        dl_cmd = ytdlp_svc.build_download_command(
            job.url,
            job_id,
            dl_template,
            embed_metadata=job.embed_metadata,
            embed_thumbnail=job.embed_thumbnail,
            embed_chapters=job.embed_chapters,
        )
        log(f"Running: {dl_cmd}")

        # Ensure archive parent dir exists
        if settings.archive_file:
            settings.archive_file.parent.mkdir(parents=True, exist_ok=True)

        dl_success = _run_subprocess(dl_cmd, log, check_cancelled=check_cancelled_cb)
        if not dl_success:
            if check_cancelled_cb():
                log("Job execution halted due to cancellation.")
                if settings.cleanup_temp_on_failure:
                    fs.cleanup_work_dir(job_id)
                return
            _fail(db, job, log, "yt-dlp download failed", log_fh, started_at)
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        if check_cancelled_cb():
            log("Job execution halted due to cancellation.")
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        # ── Find downloaded file ──────────────────────────────────────────────
        sync_update_job(db, job, phase="postprocessing")
        db.commit()
        log("Phase: postprocessing — locating downloaded file")

        downloaded_file = ytdlp_svc.find_downloaded_file(job_id)
        if downloaded_file is None:
            # Check if it was skipped because of the yt-dlp download archive
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

            _fail(
                db,
                job,
                log,
                err_msg,
                log_fh,
                started_at,
            )
            return
        log(f"Found downloaded file: {downloaded_file}")

        if check_cancelled_cb():
            log("Job execution halted due to cancellation.")
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        # ── Remux to .m4b ─────────────────────────────────────────────────────
        sync_update_job(db, job, status=JobStatus.converting, phase="converting")
        db.commit()
        log("Phase: converting — remuxing to .m4b")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        remux_result = ffmpeg_svc.run_remux(
            downloaded_file, output_path, log_fh, check_cancelled=check_cancelled_cb
        )
        if not remux_result.success:
            if check_cancelled_cb():
                log("Job execution halted due to cancellation.")
                if settings.cleanup_temp_on_failure:
                    fs.cleanup_work_dir(job_id)
                return
            _fail(
                db,
                job,
                log,
                f"ffmpeg remux failed: {remux_result.error}",
                log_fh,
                started_at,
            )
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        if remux_result.used_fallback:
            log("Note: ffmpeg used audio-only fallback (cover art was dropped)")

        if check_cancelled_cb():
            log("Job execution halted due to cancellation.")
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        # ── Verify ────────────────────────────────────────────────────────────
        sync_update_job(db, job, status=JobStatus.verifying, phase="verifying")
        db.commit()
        log("Phase: verifying output")

        try:
            probe = ffmpeg_svc.verify_output(output_path)
            log(
                f"Verification OK — size={probe.file_size} bytes, "
                f"codec={probe.codec_name}, chapters={probe.chapter_count}"
            )
            sync_update_job(db, job, chapter_count=probe.chapter_count)
            db.commit()
        except (FileNotFoundError, RuntimeError) as exc:
            _fail(db, job, log, f"Output verification failed: {exc}", log_fh, started_at)
            return

        if check_cancelled_cb():
            log("Job execution halted due to cancellation.")
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        # ── Audiobookshelf scan ───────────────────────────────────────────────
        if job.trigger_abs_scan and settings.abs_scan_after_success:
            sync_update_job(db, job, status=JobStatus.scanning, phase="scanning")
            db.commit()
            log("Phase: scanning — triggering Audiobookshelf library scan")
            scan_result = abs_client.trigger_scan()
            if scan_result.skipped:
                log("ABS scan skipped (not configured)")
            elif scan_result.success:
                log("ABS scan triggered successfully")
            else:
                log(f"ABS scan failed (non-fatal): {scan_result.error}")

        if check_cancelled_cb():
            log("Job execution halted due to cancellation.")
            if settings.cleanup_temp_on_failure:
                fs.cleanup_work_dir(job_id)
            return

        # ── Cleanup ────────────────────────────────────────────────────────────
        if settings.cleanup_temp_on_success:
            log("Cleaning up work directory")
            fs.cleanup_work_dir(job_id)

        # ── Done ──────────────────────────────────────────────────────────────
        sync_update_job(
            db,
            job,
            status=JobStatus.succeeded,
            phase="succeeded",
            final_output_path=str(output_path),
        )
        db.commit()
        sync_record_attempt(
            db,
            job,
            status="succeeded",
            started_at=started_at,
            finished_at=datetime.now(tz=UTC),
        )
        db.commit()

        log(f"=== Job {job_id} completed successfully ===")
        log(f"Output: {output_path}")
        log_fh.close()

    except Exception as exc:
        logger.exception("Unhandled error in job %s", job_id)
        try:
            job = sync_get_job(db, job_id)
            if job and job.status != JobStatus.cancelled:
                sync_update_job(
                    db,
                    job,
                    status=JobStatus.failed,
                    phase="failed",
                    error_message=str(exc),
                )
                db.commit()
                sync_record_attempt(
                    db,
                    job,
                    status="failed",
                    error_message=str(exc),
                    started_at=started_at,
                    finished_at=datetime.now(tz=UTC),
                )
                db.commit()
        except Exception:
            logger.exception("Could not record job failure in DB")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_subprocess(
    cmd: list[str],
    log: Callable[[str], None],
    check_cancelled: Callable[[], bool] | None = None,
) -> bool:
    """
    Run *cmd* as a subprocess, streaming stdout/stderr to *log*.

    Returns True if exit code is 0.
    Never uses shell=True.
    """
    log(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as exc:
        log(f"ERROR: could not start process: {exc}")
        return False

    import time

    last_check = time.time()

    assert proc.stdout is not None
    # NOTE: Reading from stdout is blocking. If the subprocess does not output
    # anything or takes a long time, the cancellation check will be delayed
    # until the next line is read. This is a known limitation.
    for line in proc.stdout:
        log(line.rstrip())
        if check_cancelled and time.time() - last_check > 3.0:
            last_check = time.time()
            if check_cancelled():
                log("Cancellation requested. Terminating subprocess...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                log("Subprocess terminated.")
                return False

    proc.wait()
    if proc.returncode != 0:
        log(f"Process exited with code {proc.returncode}")
        return False
    return True


def _fail(
    db: Session,
    job: Job,
    log: Callable[[str], None],
    message: str,
    log_fh: object,
    started_at: datetime,
) -> None:
    """Mark job as failed and record attempt."""
    log(f"FAILED: {message}")
    sync_update_job(
        db,
        job,
        status=JobStatus.failed,
        phase="failed",
        error_message=message,
    )
    db.commit()
    sync_record_attempt(
        db,
        job,
        status="failed",
        error_message=message,
        started_at=started_at,
        finished_at=datetime.now(tz=UTC),
    )
    db.commit()
    with contextlib.suppress(Exception):
        log_fh.close()  # type: ignore[attr-defined]
