"""Jobs API routes."""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models import JobStatus
from app.queue import enqueue_job_task
from app.routes import DbDep, SettingsDep
from app.serializers import job_dict
from app.services.audiobookshelf import AudiobookshelfClient
from app.services.filesystem import FilesystemService
from app.services.jobs import (
    DuplicateVideoError,
    InvalidJobUrlError,
    JobSubmitParams,
    delete_jobs,
    get_job,
    get_recent_jobs,
    submit_job,
    update_job_status,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
abs_router = APIRouter(prefix="/api/audiobookshelf", tags=["audiobookshelf"])


@router.get("")
async def api_list_jobs(db: DbDep) -> dict[str, Any]:
    jobs = await get_recent_jobs(db)
    return {"jobs": [job_dict(j) for j in jobs]}


@router.post("", status_code=201)
async def api_create_job(
    db: DbDep,
    cfg: SettingsDep,
    url: str = Form(...),
    video_id: str = Form(""),
    source_title: str = Form(""),
    uploader: str = Form(""),
    uploader_id: str = Form(""),
    channel: str = Form(""),
    channel_id: str = Form(""),
    duration: int = Form(0),
    upload_date: str = Form(""),
    thumbnail_url: str = Form(""),
    chapter_count: int = Form(0),
    output_title: str = Form(""),
    destination_folder: str = Form(""),
    new_folder: str = Form(""),
    embed_metadata: bool = Form(True),
    embed_thumbnail: bool = Form(True),
    embed_chapters: bool = Form(True),
    trigger_abs_scan: bool = Form(False),
    allow_reimport: bool = Form(False),
) -> JSONResponse:
    params = JobSubmitParams(
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
        output_title=output_title,
        destination_folder=destination_folder,
        new_folder=new_folder,
        embed_metadata=embed_metadata,
        embed_thumbnail=embed_thumbnail,
        embed_chapters=embed_chapters,
        trigger_abs_scan=trigger_abs_scan,
        allow_reimport=allow_reimport,
    )
    try:
        job, rq_id = await submit_job(db, cfg, params)
    except InvalidJobUrlError as exc:
        raise HTTPException(status_code=400, detail=exc.error) from exc
    except DuplicateVideoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse({"job_id": job.id, "rq_job_id": rq_id}, status_code=201)


@router.get("/{job_id}")
async def api_get_job(job_id: str, db: DbDep) -> dict[str, Any]:
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_dict(job)


@router.get("/{job_id}/log")
async def api_get_log(job_id: str, db: DbDep, cfg: SettingsDep) -> dict[str, str]:
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    fs = FilesystemService(cfg)
    log_path = fs.log_path(job_id)
    if not log_path.exists():
        return {"log": ""}
    return {"log": log_path.read_text(encoding="utf-8", errors="replace")}


@router.post("/{job_id}/retry")
async def api_retry_job(job_id: str, db: DbDep, cfg: SettingsDep) -> dict[str, str]:
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {JobStatus.failed, JobStatus.cancelled}:
        raise HTTPException(
            status_code=409,
            detail=f"Job status is '{job.status}', can only retry failed/cancelled jobs",
        )
    await update_job_status(db, job_id, JobStatus.queued, phase="queued", error_message="")
    rq_id = enqueue_job_task(job_id)
    await update_job_status(db, job_id, JobStatus.queued, rq_job_id=rq_id)
    return {"job_id": job_id, "rq_job_id": rq_id, "status": "queued"}


@router.post("/{job_id}/cancel")
async def api_cancel_job(job_id: str, db: DbDep) -> dict[str, str]:
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.rq_job_id:
        with contextlib.suppress(Exception):
            from rq.job import Job as RqJob

            from app.queue import get_redis

            rq_job = RqJob.fetch(job.rq_job_id, connection=get_redis())
            rq_job.cancel()
    await update_job_status(db, job_id, JobStatus.cancelled)
    return {"job_id": job_id, "status": "cancelled"}


@router.post("/delete")
async def api_delete_jobs(request: Request, db: DbDep) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    job_ids = data.get("job_ids")
    if not isinstance(job_ids, list):
        raise HTTPException(status_code=400, detail="'job_ids' must be an array")

    result = await delete_jobs(db, job_ids)

    return {
        "deleted_ids": result["deleted_ids"],
        "missing_ids": result["missing_ids"],
        "deleted_count": len(result["deleted_ids"]),
    }


@abs_router.post("/scan")
async def api_abs_scan(cfg: SettingsDep) -> dict[str, Any]:
    client = AudiobookshelfClient(cfg)
    result = client.trigger_scan()
    return {
        "success": result.success,
        "skipped": result.skipped,
        "error": result.error,
    }
