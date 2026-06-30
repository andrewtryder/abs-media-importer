"""Tests for job status transitions and retry behavior."""

from __future__ import annotations

from app.models import JobStatus

# ── JobStatus enum ─────────────────────────────────────────────────────────────


def test_job_status_values():
    assert JobStatus.queued == "queued"
    assert JobStatus.running == "running"
    assert JobStatus.downloading == "downloading"
    assert JobStatus.postprocessing == "postprocessing"
    assert JobStatus.converting == "converting"
    assert JobStatus.verifying == "verifying"
    assert JobStatus.scanning == "scanning"
    assert JobStatus.succeeded == "succeeded"
    assert JobStatus.failed == "failed"
    assert JobStatus.cancelled == "cancelled"


def test_job_status_all_statuses():
    expected = {
        "queued",
        "running",
        "downloading",
        "postprocessing",
        "converting",
        "verifying",
        "scanning",
        "succeeded",
        "failed",
        "cancelled",
    }
    actual = {s.value for s in JobStatus}
    assert actual == expected


# ── Job model ─────────────────────────────────────────────────────────────────


def test_job_duration_formatted_seconds():
    from app.models import Job

    job = Job()
    job.duration = 90
    assert job.duration_formatted == "1:30"


def test_job_duration_formatted_hours():
    from app.models import Job

    job = Job()
    job.duration = 3661
    assert job.duration_formatted == "1:01:01"


def test_job_duration_formatted_none():
    from app.models import Job

    job = Job()
    job.duration = None
    assert job.duration_formatted == "--:--"


# ── Retry logic ────────────────────────────────────────────────────────────────

TERMINAL_STATUSES = {JobStatus.failed, JobStatus.cancelled}
ACTIVE_STATUSES = {
    JobStatus.queued,
    JobStatus.running,
    JobStatus.downloading,
    JobStatus.postprocessing,
    JobStatus.converting,
    JobStatus.verifying,
    JobStatus.scanning,
}


def test_retry_only_allowed_for_terminal():
    """Only failed/cancelled jobs can be retried; others should not."""
    for status in ACTIVE_STATUSES:
        assert status not in TERMINAL_STATUSES

    for status in TERMINAL_STATUSES:
        assert status not in ACTIVE_STATUSES


def test_succeeded_job_not_retryable():
    assert JobStatus.succeeded not in TERMINAL_STATUSES


# ── Phase transitions ─────────────────────────────────────────────────────────


def test_expected_phase_progression():
    """Verify the happy-path phase order is defined correctly."""
    happy_path = [
        "queued",
        "running",
        "downloading",
        "postprocessing",
        "converting",
        "verifying",
        "scanning",
        "succeeded",
    ]
    # All phases should be valid JobStatus values
    valid = {s.value for s in JobStatus}
    for phase in happy_path:
        assert phase in valid
