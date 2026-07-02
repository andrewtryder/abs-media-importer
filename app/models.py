"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    downloading = "downloading"
    postprocessing = "postprocessing"
    converting = "converting"
    verifying = "verifying"
    scanning = "scanning"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class CollisionMode(enum.StrEnum):
    skip = "skip"
    overwrite = "overwrite"
    append_id = "append_id"
    append_counter = "append_counter"


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Source
    url: Mapped[str] = mapped_column(Text, nullable=False)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploader: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploader_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    chapter_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Output configuration
    output_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collision_mode: Mapped[str] = mapped_column(String(20), default="append_id")

    # Job options (stored as booleans)
    embed_metadata: Mapped[bool] = mapped_column(Boolean, default=True)
    embed_thumbnail: Mapped[bool] = mapped_column(Boolean, default=True)
    embed_chapters: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_abs_scan: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_reimport: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(
        Enum(JobStatus),
        default=JobStatus.queued,
        nullable=False,
    )
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    progress_eta: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress_speed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Paths
    work_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # RQ job id
    rq_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    attempts_log: Mapped[list[JobAttempt]] = relationship(
        "JobAttempt", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id!r} status={self.status!r}>"

    @property
    def duration_formatted(self) -> str:
        """Return HH:MM:SS string."""
        if self.duration is None:
            return "--:--"
        h, remainder = divmod(self.duration, 3600)
        m, s = divmod(remainder, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# ImportedVideo — canonical dedup ledger
# ---------------------------------------------------------------------------


class ImportedVideo(Base):
    __tablename__ = "imported_videos"

    # One row per successfully imported YouTube video.
    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# JobAttempt — tracks each retry
# ---------------------------------------------------------------------------


class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rq_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    artifact_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship("Job", back_populates="attempts_log")
