"""Browser extension API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth import ExtensionAuthDep
from app.routes import DbDep
from app.services.jobs import DuplicateVideoError, InvalidJobUrlError, JobSubmitParams, submit_job
from app.services.ytdlp import YtDlpService

router = APIRouter(prefix="/api/extension", tags=["extension"])


@router.get("/status")
async def api_extension_status(cfg: ExtensionAuthDep) -> dict[str, Any]:
    return {
        "ok": True,
        "app": "reeldock",
        "extension_api_enabled": cfg.extension_api_enabled,
        "auth_required": bool(cfg.extension_api_token),
        "dry_run": cfg.dry_run,
        "abs_configured": cfg.abs_configured,
        "allow_playlists": cfg.allow_playlists,
        "allow_channels": cfg.allow_channels,
    }


@router.post("/queue", status_code=201)
async def api_extension_queue(
    request: Request,
    db: DbDep,
    cfg: ExtensionAuthDep,
) -> JSONResponse:
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    url = data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    svc = YtDlpService(cfg)
    validation = svc.validate_url(url)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.error)

    try:
        meta = svc.run_preview(url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    destination_folder = data.get("destination_folder", "")
    output_title = data.get("output_title", "")
    embed_metadata = data.get("embed_metadata", True)
    embed_thumbnail = data.get("embed_thumbnail", True)
    embed_chapters = data.get("embed_chapters", True)
    trigger_abs_scan = data.get("trigger_abs_scan", False)
    allow_reimport = data.get("allow_reimport", False)
    if isinstance(allow_reimport, str):
        allow_reimport = allow_reimport.strip().lower() in {"1", "true", "yes", "on"}
    else:
        allow_reimport = bool(allow_reimport)

    params = JobSubmitParams(
        url=url,
        video_id=meta.id,
        source_title=meta.title,
        uploader=meta.uploader,
        uploader_id=meta.uploader_id,
        channel=meta.channel,
        channel_id=meta.channel_id,
        duration=meta.duration,
        upload_date=meta.upload_date,
        thumbnail_url=meta.thumbnail,
        chapter_count=meta.chapter_count,
        output_title=output_title or meta.title,
        destination_folder=destination_folder or cfg.default_destination_folder,
        embed_metadata=embed_metadata,
        embed_thumbnail=embed_thumbnail,
        embed_chapters=embed_chapters,
        trigger_abs_scan=trigger_abs_scan,
        allow_reimport=allow_reimport,
        validate_url=False,
    )

    try:
        job, rq_id = await submit_job(db, cfg, params)
    except InvalidJobUrlError as exc:
        raise HTTPException(status_code=400, detail=exc.error) from exc
    except DuplicateVideoError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "ok": True,
            "job_id": job.id,
            "rq_job_id": rq_id,
            "status": "queued",
            "title": meta.title,
            "uploader": meta.uploader,
            "job_url": f"/jobs/{job.id}",
        },
        status_code=201,
    )
