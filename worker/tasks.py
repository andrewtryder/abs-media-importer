"""RQ worker task: run_import_job.

This module is the entry point for background import jobs.
It is executed by the RQ worker process (not inside FastAPI's event loop).
All I/O is synchronous.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.config import get_settings
from app.db import get_sync_db
from app.models import JobStatus
from app.services.import_pipeline import ImportPipeline
from app.services.jobs import sync_get_job, sync_record_attempt, sync_update_job

logger = logging.getLogger(__name__)


def run_import_job(job_id: str) -> None:
    """
    Execute the full import pipeline for a job.
    """
    settings = get_settings()
    db = get_sync_db()
    started_at = datetime.now(tz=UTC)

    try:
        job = sync_get_job(db, job_id)
        if job is None:
            logger.error("Job %s not found in database", job_id)
            return

        pipeline = ImportPipeline(db, settings, job_id)
        pipeline.run()

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
