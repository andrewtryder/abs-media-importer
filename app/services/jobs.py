"""Job service: create, update, and query jobs in the database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Job, JobAttempt, JobStatus


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Async helpers (FastAPI routes)
# ---------------------------------------------------------------------------


async def create_job(
    session: AsyncSession,
    url: str,
    settings: Settings,
    *,
    video_id: str | None = None,
    source_title: str | None = None,
    uploader: str | None = None,
    uploader_id: str | None = None,
    channel: str | None = None,
    channel_id: str | None = None,
    duration: int | None = None,
    upload_date: str | None = None,
    thumbnail_url: str | None = None,
    chapter_count: int | None = None,
    output_title: str | None = None,
    destination_folder: str | None = None,
    embed_metadata: bool = True,
    embed_thumbnail: bool = True,
    embed_chapters: bool = True,
    trigger_abs_scan: bool = False,
) -> Job:
    """Persist a new Job record and return it."""
    job = Job(
        id=str(uuid.uuid4()),
        url=url,
        video_id=video_id,
        source_title=source_title,
        uploader=uploader,
        uploader_id=uploader_id,
        channel=channel,
        channel_id=channel_id,
        duration=duration,
        upload_date=upload_date,
        thumbnail_url=thumbnail_url,
        chapter_count=chapter_count,
        output_title=output_title or source_title,
        destination_folder=destination_folder or settings.default_destination_folder,
        embed_metadata=embed_metadata,
        embed_thumbnail=embed_thumbnail,
        embed_chapters=embed_chapters,
        trigger_abs_scan=trigger_abs_scan,
        collision_mode=settings.collision_mode,
        status=JobStatus.queued,
        attempts=0,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, job_id: str) -> Job | None:
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def get_recent_jobs(session: AsyncSession, limit: int = 50) -> list[Job]:
    result = await session.execute(select(Job).order_by(desc(Job.created_at)).limit(limit))
    return list(result.scalars().all())


async def update_job_status(
    session: AsyncSession,
    job_id: str,
    status: JobStatus,
    phase: str | None = None,
    error_message: str | None = None,
    final_output_path: str | None = None,
    rq_job_id: str | None = None,
    progress: int | None = None,
    progress_percent: float | None = None,
    progress_eta: str | None = None,
    progress_speed: str | None = None,
    progress_label: str | None = None,
) -> Job | None:
    job = await get_job(session, job_id)
    if job is None:
        return None
    job.status = status
    job.updated_at = _utcnow()
    if phase is not None:
        job.phase = phase
    if error_message is not None:
        job.error_message = error_message
    if final_output_path is not None:
        job.final_output_path = final_output_path
    if rq_job_id is not None:
        job.rq_job_id = rq_job_id
    if progress is not None:
        job.progress = progress
    if progress_percent is not None:
        job.progress_percent = progress_percent
    if progress_eta is not None:
        job.progress_eta = progress_eta
    if progress_speed is not None:
        job.progress_speed = progress_speed
    if progress_label is not None:
        job.progress_label = progress_label

    if status == JobStatus.queued:
        job.progress = None
        job.progress_percent = None
        job.progress_eta = None
        job.progress_speed = None
        job.progress_label = None

    if status == JobStatus.running and job.started_at is None:
        job.started_at = _utcnow()
    if status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
        job.finished_at = _utcnow()
    await session.commit()
    await session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Sync helpers (RQ worker)
# ---------------------------------------------------------------------------


def sync_get_job(session: Session, job_id: str) -> Job | None:
    return session.get(Job, job_id)


def sync_update_job(
    session: Session,
    job: Job,
    *,
    status: JobStatus | None = None,
    phase: str | None = None,
    error_message: str | None = None,
    final_output_path: str | None = None,
    log_file_path: str | None = None,
    work_dir: str | None = None,
    rq_job_id: str | None = None,
    chapter_count: int | None = None,
    progress: int | None = None,
    progress_percent: float | None = None,
    progress_eta: str | None = None,
    progress_speed: str | None = None,
    progress_label: str | None = None,
) -> None:
    """Update job fields and flush to DB (no commit — caller commits)."""
    now = _utcnow()
    job.updated_at = now

    if status is not None:
        job.status = status
        if status == JobStatus.running and job.started_at is None:
            job.started_at = now
        if status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
            job.finished_at = now
        if status == JobStatus.queued:
            job.progress = None
            job.progress_percent = None
            job.progress_eta = None
            job.progress_speed = None
            job.progress_label = None
    if phase is not None:
        job.phase = phase
    if error_message is not None:
        job.error_message = error_message
    if final_output_path is not None:
        job.final_output_path = final_output_path
    if log_file_path is not None:
        job.log_file_path = log_file_path
    if work_dir is not None:
        job.work_dir = work_dir
    if rq_job_id is not None:
        job.rq_job_id = rq_job_id
    if chapter_count is not None:
        job.chapter_count = chapter_count
    if progress is not None:
        job.progress = progress
    if progress_percent is not None:
        job.progress_percent = progress_percent
    if progress_eta is not None:
        job.progress_eta = progress_eta
    if progress_speed is not None:
        job.progress_speed = progress_speed
    if progress_label is not None:
        job.progress_label = progress_label

    session.flush()


def sync_record_attempt(
    session: Session,
    job: Job,
    *,
    status: str,
    rq_job_id: str | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    artifact_metadata: str | None = None,
) -> JobAttempt:
    """Append a JobAttempt record for the given job."""
    attempt = JobAttempt(
        id=str(uuid.uuid4()),
        job_id=job.id,
        attempt_number=job.attempts,
        status=status,
        rq_job_id=rq_job_id,
        error_message=error_message,
        started_at=started_at or _utcnow(),
        finished_at=finished_at,
        artifact_metadata=artifact_metadata,
    )
    session.add(attempt)
    session.flush()
    return attempt
