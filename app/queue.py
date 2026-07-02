"""Redis + RQ queue configuration."""

from __future__ import annotations

from redis import Redis
from rq import Queue

from app.config import get_settings

QUEUE_NAME = "abs_media_importer"

_redis_conn: Redis | None = None
_queue: Queue | None = None


def get_redis() -> Redis:
    global _redis_conn
    if _redis_conn is None:
        settings = get_settings()
        _redis_conn = Redis.from_url(settings.redis_url)
    return _redis_conn


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        settings = get_settings()
        _queue = Queue(
            QUEUE_NAME,
            connection=get_redis(),
            default_timeout=settings.job_timeout_seconds,
        )
    return _queue


def enqueue_job_task(job_id: str) -> str:
    """Enqueue the import task for *job_id* and return the RQ job id."""
    from worker.tasks import run_import_job  # avoid circular import at module level

    settings = get_settings()
    rq_job = get_queue().enqueue(
        run_import_job,
        job_id,
        job_timeout=settings.job_timeout_seconds,
        retry=_build_rq_retry(),
    )
    return str(rq_job.id)


def _build_rq_retry() -> object | None:
    """Build an rq.Retry object from config, if rq supports it."""
    try:
        from rq import Retry  # rq >= 1.10

        settings = get_settings()
        intervals = settings.retry_interval_seconds[: settings.retry_max]
        # Pad or trim to match retry_max
        while len(intervals) < settings.retry_max:
            intervals.append(intervals[-1] if intervals else 60)
        return Retry(max=settings.retry_max, interval=intervals)
    except ImportError:
        return None
