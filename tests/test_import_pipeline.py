"""Tests for ImportPipeline orchestration, progress tracking, and cancellation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.config import Settings
from app.models import Base, Job, JobStatus
from app.services.ffmpeg import FfprobeResult, RemuxResult
from app.services.import_pipeline import ImportPipeline
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database and session factory."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Mock Settings object wired to tmp paths."""
    s = Settings()
    s.output_root = tmp_path / "podcasts"
    s.work_dir = tmp_path / "work"
    s.archive_file = tmp_path / "archive.txt"
    s.ytdlp_bin = "yt-dlp"
    s.ffmpeg_bin = "ffmpeg"
    s.ffprobe_bin = "ffprobe"
    s.dry_run = False
    s.cleanup_temp_on_success = True
    s.cleanup_temp_on_failure = True
    return s


def test_pipeline_dry_run(test_db, mock_settings):
    """Verify dry run mode creates fake files and succeeds immediately without subprocesses."""
    mock_settings.dry_run = True

    # Setup database job
    job = Job(
        id="job-dry",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Dry Run Test",
        destination_folder="Podcasts",
    )
    test_db.add(job)
    test_db.commit()

    pipeline = ImportPipeline(test_db, mock_settings, "job-dry")
    pipeline.run()

    test_db.refresh(job)
    assert job.status == JobStatus.succeeded
    assert job.phase == "succeeded"
    assert job.final_output_path is not None
    assert Path(job.final_output_path).name == "Dry Run Test.m4b"
    assert Path(job.final_output_path).exists()
    assert job.output_file_size == Path(job.final_output_path).stat().st_size
    assert len(job.attempts_log) == 1
    assert job.attempts_log[0].status == "succeeded"
    # DRY RUN: progress should be 100% complete
    assert job.progress_percent == 100.0
    assert job.progress_label == "Complete"


@patch("app.services.process_runner.subprocess.Popen")
@patch("app.services.import_pipeline.YtDlpService.find_downloaded_file")
@patch("app.services.import_pipeline.FfmpegService.run_remux")
@patch("app.services.import_pipeline.FfmpegService.verify_output")
def test_pipeline_happy_path(
    mock_verify, mock_remux, mock_find, mock_popen, test_db, mock_settings, tmp_path
):
    """Verify happy path from downloading to conversion, verification, and success."""
    # Setup job
    job = Job(
        id="job-happy",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Happy Path Video",
        destination_folder="Happy",
        collision_mode="overwrite",
    )
    test_db.add(job)
    test_db.commit()

    # Mock subprocess.Popen for yt-dlp download
    mock_proc = MagicMock()
    mock_proc.stdout = [
        "[download]   0.0% of ~20.00MiB at 100KiB/s ETA 01:00\n",
        "[download]  50.0% of ~20.00MiB at 100KiB/s ETA 00:30\n",
        "[download] 100% of 20.00MiB\n",
    ]
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    # Mock finding downloaded file
    downloaded_m4a = tmp_path / "work" / "job-happy" / "download" / "Happy Path Video.m4a"
    downloaded_m4a.parent.mkdir(parents=True, exist_ok=True)
    downloaded_m4a.write_bytes(b"audio")
    mock_find.return_value = downloaded_m4a

    # Mock remux execution
    mock_remux.return_value = RemuxResult(success=True, used_fallback=False)

    # Mock verification output
    final_output = mock_settings.output_root / "Happy" / "Happy Path Video.m4b"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_bytes(b"x" * 1000)
    mock_verify.return_value = FfprobeResult(
        file_size=1000,
        has_audio=True,
        chapter_count=3,
        duration_seconds=120.0,
        codec_name="aac",
    )

    pipeline = ImportPipeline(test_db, mock_settings, "job-happy")
    pipeline.run()

    test_db.refresh(job)
    assert job.status == JobStatus.succeeded
    assert job.phase == "succeeded"
    assert job.progress == 100
    assert job.progress_percent == 100.0
    assert job.progress_label == "Complete"
    assert job.chapter_count == 3
    assert job.final_output_path == str(final_output)
    assert job.output_file_size == final_output.stat().st_size
    assert len(job.attempts_log) == 1
    assert job.attempts_log[0].status == "succeeded"

    # Verify attempt metadata
    meta = job.attempts_log[0].artifact_metadata
    assert meta is not None
    meta_dict = json.loads(meta)
    assert "download" in meta_dict
    assert "conversion" in meta_dict
    assert meta_dict["download"]["format"] == "m4a"
    assert meta_dict["conversion"]["codec_name"] == "aac"
    assert meta_dict["conversion"]["duration_seconds"] == 120.0


@patch("app.services.process_runner.subprocess.Popen")
@patch("app.services.import_pipeline.YtDlpService.find_downloaded_file")
@patch("app.services.import_pipeline.FfmpegService.run_remux")
@patch("app.services.import_pipeline.FfmpegService.verify_output")
def test_pipeline_happy_path_with_abs_scan(
    mock_verify, mock_remux, mock_find, mock_popen, test_db, mock_settings, tmp_path
):
    """Verify happy path with audiobookshelf scan triggered."""
    job = Job(
        id="job-scan",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Scan Video",
        destination_folder="Scan",
        collision_mode="overwrite",
        trigger_abs_scan=True,
    )
    test_db.add(job)
    test_db.commit()

    # Enable ABS scan in settings
    mock_settings.abs_scan_after_success = True
    mock_settings.abs_base_url = "http://abs:1337"
    mock_settings.abs_api_token = "test-token"
    mock_settings.abs_library_id = "lib-1"

    # Mock subprocess.Popen for download
    mock_proc = MagicMock()
    mock_proc.stdout = ["[download] 100% of 10.00MiB\n"]
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    # Mock finding downloaded file
    downloaded = tmp_path / "work" / "job-scan" / "download" / "Scan Video.m4a"
    downloaded.parent.mkdir(parents=True, exist_ok=True)
    downloaded.write_bytes(b"audio")
    mock_find.return_value = downloaded

    # Mock remux
    mock_remux.return_value = RemuxResult(success=True, used_fallback=False)

    # Mock verify
    final_output = mock_settings.output_root / "Scan" / "Scan Video.m4b"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_bytes(b"final m4b")
    mock_verify.return_value = FfprobeResult(
        file_size=1000, has_audio=True, chapter_count=0, duration_seconds=60.0, codec_name="aac"
    )

    # Mock ABS scan success
    with patch("app.services.import_pipeline.AudiobookshelfClient.trigger_scan") as mock_scan:
        from app.services.audiobookshelf import ScanResult

        mock_scan.return_value = ScanResult(success=True, skipped=False)

        pipeline = ImportPipeline(test_db, mock_settings, "job-scan")
        pipeline.run()

    test_db.refresh(job)
    assert job.status == JobStatus.succeeded
    assert job.progress_percent == 100.0
    assert job.progress_label == "Complete"


@patch("app.services.process_runner.subprocess.Popen")
def test_pipeline_failed_download(mock_popen, test_db, mock_settings):
    """Verify pipeline failure transitions and attempts log when download fails."""
    job = Job(
        id="job-fail-dl",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Failed Video",
        destination_folder="Fail",
    )
    test_db.add(job)
    test_db.commit()

    # Mock subprocess.Popen for yt-dlp returning exit code 1
    mock_proc = MagicMock()
    mock_proc.stdout = ["ERROR: Could not download video\n"]
    mock_proc.returncode = 1
    mock_popen.return_value = mock_proc

    pipeline = ImportPipeline(test_db, mock_settings, "job-fail-dl")
    pipeline.run()

    test_db.refresh(job)
    assert job.status == JobStatus.failed
    assert job.phase == "failed"
    assert "yt-dlp download failed" in job.error_message
    assert job.progress_label == "Failed"
    assert job.progress_eta == ""
    assert job.progress_speed == ""
    assert len(job.attempts_log) == 1
    assert job.attempts_log[0].status == "failed"
    assert "yt-dlp download failed" in job.attempts_log[0].error_message


@patch("app.services.process_runner.subprocess.Popen")
@patch("app.services.import_pipeline.YtDlpService.find_downloaded_file")
@patch("app.services.import_pipeline.FfmpegService.run_remux")
@patch("app.services.import_pipeline.FfmpegService.verify_output")
def test_pipeline_failed_verification(
    mock_verify, mock_remux, mock_find, mock_popen, test_db, mock_settings, tmp_path
):
    """Verify job transitions to failed if final verification fails."""
    job = Job(
        id="job-fail-verify",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Failed Verify Video",
        destination_folder="FailVerify",
    )
    test_db.add(job)
    test_db.commit()

    # Mock subprocess.Popen for yt-dlp
    mock_proc = MagicMock()
    mock_proc.stdout = ["[download] 100% of 10.00MiB\n"]
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    # Mock finding downloaded file
    downloaded_m4a = tmp_path / "work" / "job-fail-verify" / "download" / "video.m4a"
    downloaded_m4a.parent.mkdir(parents=True, exist_ok=True)
    downloaded_m4a.write_bytes(b"audio")
    mock_find.return_value = downloaded_m4a

    # Mock remux execution
    mock_remux.return_value = RemuxResult(success=True, used_fallback=False)

    # Mock verification throwing RuntimeError
    mock_verify.side_effect = RuntimeError("No audio stream found")

    pipeline = ImportPipeline(test_db, mock_settings, "job-fail-verify")
    pipeline.run()

    test_db.refresh(job)
    assert job.status == JobStatus.failed
    assert job.phase == "failed"
    assert "Output verification failed: No audio stream found" in job.error_message
    assert job.progress_label == "Failed"
    assert job.progress_eta == ""
    assert job.progress_speed == ""
    assert len(job.attempts_log) == 1
    assert job.attempts_log[0].status == "failed"


@patch("app.services.process_runner.subprocess.Popen")
def test_pipeline_cancellation(mock_popen, test_db, mock_settings):
    """Verify cancellation terminates the active subprocess and marks the job cancelled."""
    job = Job(
        id="job-cancel",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Cancelled Video",
        destination_folder="Cancel",
    )
    test_db.add(job)
    test_db.commit()

    # Mock a subprocess that gets cancelled mid-stream
    # We will simulate the cancellation callback detecting cancelled status in the DB
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    def mock_terminate():
        mock_proc.poll.return_value = -15

    mock_proc.terminate.side_effect = mock_terminate

    # Custom iterator to change job status during execution
    class CancelStream:
        def __init__(self, db, job):
            self.db = db
            self.job = job
            self.yielded = False

        def __iter__(self):
            return self

        def __next__(self):
            if not self.yielded:
                # Mark job as cancelled in the DB using a separate session for thread safety
                from sqlalchemy.orm import sessionmaker

                SessionLocal = sessionmaker(bind=self.db.bind)
                with SessionLocal() as local_session:
                    local_job = local_session.get(self.job.__class__, self.job.id)
                    if local_job:
                        local_job.status = JobStatus.cancelled
                        local_session.commit()
                self.yielded = True
                return "[download] Starting download...\n"
            else:
                raise StopIteration()

    mock_proc.stdout = CancelStream(test_db, job)
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    # Force checking cancellation frequently — provide enough values for all
    # time.time() calls made by _set_progress and the process runner loop.
    time_values = [0.0, 2.0, 3.0, 4.0, 5.0]
    while len(time_values) < 30:
        time_values.append(time_values[-1] + 0.5)
    with patch("time.time", side_effect=time_values):
        pipeline = ImportPipeline(test_db, mock_settings, "job-cancel")
        pipeline.run()

    test_db.refresh(job)
    assert job.status == JobStatus.cancelled
    assert job.phase == "cancelled"
    assert job.progress_label == "Cancelled"
    assert job.progress_eta == ""
    assert job.progress_speed == ""
    assert mock_proc.terminate.called
    assert len(job.attempts_log) == 1
    assert job.attempts_log[0].status == "cancelled"


# ── Process Runner & Schema Validation ──────────────────────────────────────


def test_run_streaming_process_cancellation():
    import sys

    from app.services.process_runner import run_streaming_process

    # Execute a small Python program that prints a line and sleeps
    cmd = [
        sys.executable,
        "-c",
        "import time; [print(f'step {i}', flush=True) or time.sleep(0.1) for i in range(20)]",
    ]

    lines_received = []

    def log_line(line: str) -> None:
        lines_received.append(line)

    # Cancel after we have read 2 lines
    def check_cancelled() -> bool:
        return len(lines_received) >= 2

    res = run_streaming_process(
        cmd,
        log_line=log_line,
        check_cancelled=check_cancelled,
        cancel_check_interval=0.05,
        terminate_timeout=1.0,
    )

    assert res.cancelled is True
    assert len(lines_received) >= 2
    assert len(lines_received) < 20  # Cancelled early, did not complete all 20 lines


def test_database_migration_columns(test_db):
    """Verify that Job and JobAttempt models have the new progress and metadata fields."""
    # The test_db fixture automatically calls metadata.create_all,
    # which uses the updated model definitions.
    connection = test_db.connection()

    # Check jobs columns
    cursor = connection.execute(text("PRAGMA table_info(jobs)"))
    cols = [row[1] for row in cursor.fetchall()]
    assert "progress" in cols
    assert "progress_percent" in cols
    assert "progress_eta" in cols
    assert "progress_speed" in cols
    assert "progress_label" in cols
    assert "output_file_size" in cols

    # Check job_attempts columns
    cursor_attempts = connection.execute(text("PRAGMA table_info(job_attempts)"))
    attempts_cols = [row[1] for row in cursor_attempts.fetchall()]
    assert "artifact_metadata" in attempts_cols


# ── Progress mapping helpers ───────────────────────────────────────────────


def test_map_range():
    """Verify _map_range correctly scales values into target ranges."""
    # 0.0 -> start, 1.0 -> end
    assert ImportPipeline._map_range(0.0, 2.0, 70.0) == 2.0
    assert ImportPipeline._map_range(0.5, 2.0, 70.0) == pytest.approx(36.0)
    assert ImportPipeline._map_range(1.0, 2.0, 70.0) == 70.0

    # Clamping
    assert ImportPipeline._map_range(-0.5, 2.0, 70.0) == 0.0
    assert ImportPipeline._map_range(1.5, 2.0, 70.0) == 100.0

    # Conversion range 72-90%
    assert ImportPipeline._map_range(0.0, 72.0, 90.0) == 72.0
    assert ImportPipeline._map_range(0.5, 72.0, 90.0) == 81.0
    assert ImportPipeline._map_range(1.0, 72.0, 90.0) == 90.0


def test_download_progress_mapping():
    """Verify yt-dlp percent maps into overall 2-70% range."""
    # 0% -> 2%
    assert ImportPipeline._map_range(0.0 / 100.0, 2.0, 70.0) == 2.0
    # 50% -> 36%
    assert ImportPipeline._map_range(50.0 / 100.0, 2.0, 70.0) == 36.0
    # 100% -> 70%
    assert ImportPipeline._map_range(100.0 / 100.0, 2.0, 70.0) == 70.0


def test_conversion_progress_mapping_with_duration():
    """Verify ffmpeg out_time maps into 72-90% when duration is known."""
    # out_time=0, duration=100 -> 72% (ratio 0.0)
    assert ImportPipeline._map_range(0.0 / 100.0, 72.0, 90.0) == 72.0
    # out_time=50, duration=100 -> 81% (ratio 0.5)
    assert ImportPipeline._map_range(50.0 / 100.0, 72.0, 90.0) == 81.0
    # out_time=100, duration=100 -> 90% (ratio 1.0)
    assert ImportPipeline._map_range(100.0 / 100.0, 72.0, 90.0) == 90.0
    # out_time=200, duration=100 -> 90% clamped
    assert ImportPipeline._map_range(200.0 / 100.0, 72.0, 90.0) == 100.0  # clamped by _map_range


def test_set_progress_clamping(test_db, mock_settings):
    """Verify _set_progress clamps percent to 0-100."""
    job = Job(
        id="job-clamp",
        url="https://youtube.com/watch?v=123",
        status=JobStatus.queued,
        output_title="Clamp Test",
        destination_folder="Clamp",
    )
    test_db.add(job)
    test_db.commit()

    pipeline = ImportPipeline(test_db, mock_settings, "job-clamp")

    # Set valid percent
    pipeline._set_progress(job, percent=50.0, label="Halfway", force=True)
    test_db.refresh(job)
    assert 49.0 <= job.progress_percent <= 51.0
    assert job.progress_label == "Halfway"

    # Set negative — should clamp to 0
    pipeline._set_progress(job, percent=-10.0, label="Negative", force=True)
    test_db.refresh(job)
    assert job.progress_percent == 0.0
    assert job.progress_label == "Negative"

    # Set above 100 — should clamp to 100
    pipeline._set_progress(job, percent=150.0, label="Overflow", force=True)
    test_db.refresh(job)
    assert job.progress_percent == 100.0
    assert job.progress_label == "Overflow"

    # Label-only update
    pipeline._set_progress(job, label="Label only", force=True)
    test_db.refresh(job)
    assert job.progress_percent == 100.0  # unchanged
    assert job.progress_label == "Label only"
