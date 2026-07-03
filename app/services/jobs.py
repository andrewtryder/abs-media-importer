"""Job service: create, update, and query jobs in the database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ImportedVideo, Job, JobAttempt, JobStatus
from app.queue import enqueue_job_task
from app.services.filesystem import FilesystemService
from app.services.ytdlp import YtDlpService


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class DuplicateVideoError(ValueError):
    """Raised when a video has already been imported previously."""


class InvalidJobUrlError(ValueError):
    """Raised when a job URL fails validation."""

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__(error)


@dataclass
class JobSubmitParams:
    url: str
    video_id: str | None = None
    source_title: str | None = None
    uploader: str | None = None
    uploader_id: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    duration: int | None = None
    upload_date: str | None = None
    thumbnail_url: str | None = None
    chapter_count: int | None = None
    output_title: str | None = None
    destination_folder: str | None = None
    new_folder: str = ""
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    embed_chapters: bool = True
    trigger_abs_scan: bool = False
    allow_reimport: bool = False
    validate_url: bool = True


def _or_none(value: str | None) -> str | None:
    return (value or "").strip() or None


def _or_none_int(value: int | None) -> int | None:
    if value is None or value == 0:
        return None
    return value


async def submit_job(
    session: AsyncSession,
    settings: Settings,
    params: JobSubmitParams,
) -> tuple[Job, str]:
    """Validate, optionally create folder, persist job, and enqueue work."""
    if params.validate_url:
        svc = YtDlpService(settings)
        validation = svc.validate_url(params.url)
        if not validation.valid:
            raise InvalidJobUrlError(validation.error or "Invalid URL")

    destination_folder = params.destination_folder or ""
    if params.new_folder.strip():
        fs = FilesystemService(settings)
        fs.create_folder(params.new_folder.strip())
        destination_folder = params.new_folder.strip()

    job = await create_job(
        session,
        params.url,
        settings,
        video_id=_or_none(params.video_id),
        source_title=_or_none(params.source_title),
        uploader=_or_none(params.uploader),
        uploader_id=_or_none(params.uploader_id),
        channel=_or_none(params.channel),
        channel_id=_or_none(params.channel_id),
        duration=_or_none_int(params.duration),
        upload_date=_or_none(params.upload_date),
        thumbnail_url=_or_none(params.thumbnail_url),
        chapter_count=_or_none_int(params.chapter_count),
        output_title=_or_none(params.output_title) or _or_none(params.source_title),
        destination_folder=_or_none(destination_folder),
        embed_metadata=params.embed_metadata,
        embed_thumbnail=params.embed_thumbnail,
        embed_chapters=params.embed_chapters,
        trigger_abs_scan=params.trigger_abs_scan,
        allow_reimport=params.allow_reimport,
    )

    rq_id = enqueue_job_task(job.id)
    await update_job_status(session, job.id, JobStatus.queued, rq_job_id=rq_id)
    return job, rq_id


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
    allow_reimport: bool = False,
) -> Job:
    """Persist a new Job record and return it."""
    normalized_video_id = (video_id or "").strip() or None
    if normalized_video_id and not allow_reimport:
        existing_import = await get_imported_video(session, normalized_video_id)
        if existing_import is not None:
            raise DuplicateVideoError(
                f"Video '{normalized_video_id}' has already been imported "
                f"(job {existing_import.job_id or 'unknown'})."
            )

    job = Job(
        id=str(uuid.uuid4()),
        url=url,
        video_id=normalized_video_id,
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
        allow_reimport=allow_reimport,
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


async def get_imported_video(session: AsyncSession, video_id: str) -> ImportedVideo | None:
    """Fetch an ImportedVideo row by video id."""
    normalized = video_id.strip()
    if not normalized:
        return None
    result = await session.execute(
        select(ImportedVideo).where(ImportedVideo.video_id == normalized)
    )
    return result.scalar_one_or_none()


async def get_job(session: AsyncSession, job_id: str) -> Job | None:
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def get_recent_jobs(session: AsyncSession, limit: int = 50) -> list[Job]:
    result = await session.execute(select(Job).order_by(desc(Job.created_at)).limit(limit))
    return list(result.scalars().all())


async def delete_jobs(session: AsyncSession, job_ids: list[str]) -> dict[str, list[str]]:
    """Delete jobs by id and return deleted/missing/blocked ids."""
    normalized_ids = []
    seen_ids: set[str] = set()
    for job_id in job_ids:
        value = (job_id or "").strip()
        if not value or value in seen_ids:
            continue
        normalized_ids.append(value)
        seen_ids.add(value)

    if not normalized_ids:
        return {"deleted_ids": [], "missing_ids": [], "blocked_ids": []}

    result = await session.execute(select(Job).where(Job.id.in_(normalized_ids)))
    jobs = list(result.scalars().all())
    found_by_id = {job.id: job for job in jobs}
    missing_ids = [job_id for job_id in normalized_ids if job_id not in found_by_id]

    deletable_ids = [job.id for job in jobs]
    if not deletable_ids:
        return {"deleted_ids": [], "missing_ids": missing_ids, "blocked_ids": []}

    # Keep the dedup ledger rows while severing references to deleted jobs.
    await session.execute(
        update(ImportedVideo).where(ImportedVideo.job_id.in_(deletable_ids)).values(job_id=None)
    )

    for job in jobs:
        await session.delete(job)
    await session.commit()

    return {"deleted_ids": deletable_ids, "missing_ids": missing_ids, "blocked_ids": []}


async def update_job_status(
    session: AsyncSession,
    job_id: str,
    status: JobStatus,
    phase: str | None = None,
    error_message: str | None = None,
    final_output_path: str | None = None,
    output_file_size: int | None = None,
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
    if output_file_size is not None:
        job.output_file_size = output_file_size
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
    output_file_size: int | None = None,
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
    if output_file_size is not None:
        job.output_file_size = output_file_size
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


def sync_mark_video_imported(session: Session, job: Job, *, overwrite: bool = False) -> bool:
    """Record a successful import in imported_videos.

    Returns True when a new row is stored or no video_id is present.
    Returns False when the video_id is already recorded.
    """
    video_id = (job.video_id or "").strip()
    if not video_id:
        return True

    existing = session.get(ImportedVideo, video_id)
    if existing is not None:
        if not overwrite:
            return False
        existing.job_id = job.id
        existing.source_url = job.url
        existing.source_title = job.source_title
        existing.imported_at = _utcnow()
        session.flush()
        return True

    record = ImportedVideo(
        video_id=video_id,
        job_id=job.id,
        source_url=job.url,
        source_title=job.source_title,
        imported_at=_utcnow(),
    )
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        session.add(job)
        if overwrite:
            existing = session.get(ImportedVideo, video_id)
            if existing is not None:
                existing.job_id = job.id
                existing.source_url = job.url
                existing.source_title = job.source_title
                existing.imported_at = _utcnow()
                session.flush()
                return True
        return False
    return True
