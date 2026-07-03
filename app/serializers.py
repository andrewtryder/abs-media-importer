"""API serialization helpers."""

from __future__ import annotations

from typing import Any

from app.models import Job


def job_dict(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "url": job.url,
        "video_id": job.video_id,
        "source_title": job.source_title,
        "output_title": job.output_title,
        "destination_folder": job.destination_folder,
        "final_output_path": job.final_output_path,
        "output_file_size": job.output_file_size,
        "status": job.status,
        "phase": job.phase,
        "progress": job.progress,
        "progress_percent": job.progress_percent,
        "progress_eta": job.progress_eta,
        "progress_speed": job.progress_speed,
        "progress_label": job.progress_label,
        "error_message": job.error_message,
        "attempts": job.attempts,
        "chapter_count": job.chapter_count,
        "allow_reimport": job.allow_reimport,
        "duration": job.duration,
        "uploader": job.uploader,
        "uploader_id": job.uploader_id,
        "channel": job.channel,
        "channel_id": job.channel_id,
        "thumbnail_url": job.thumbnail_url,
        "rq_job_id": job.rq_job_id,
        "log_file_path": job.log_file_path,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
