"""Config and preview API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException

from app.routes import SettingsDep
from app.services.filesystem import FilesystemService
from app.services.ytdlp import YtDlpService

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
async def api_config(cfg: SettingsDep) -> dict[str, Any]:
    return {
        "output_root": str(cfg.output_root),
        "allow_playlists": cfg.allow_playlists,
        "allow_channels": cfg.allow_channels,
        "abs_configured": cfg.abs_configured,
        "abs_scan_after_success": cfg.abs_scan_after_success,
        "dry_run": cfg.dry_run,
        "max_concurrent_jobs": cfg.max_concurrent_jobs,
    }


@router.get("/folders")
async def api_folders(cfg: SettingsDep) -> dict[str, list[str]]:
    fs = FilesystemService(cfg)
    return {"folders": fs.list_folders()}


@router.post("/preview")
async def api_preview(cfg: SettingsDep, url: str = Form(...)) -> dict[str, Any]:
    svc = YtDlpService(cfg)
    validation = svc.validate_url(url)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.error)
    try:
        meta = svc.run_preview(url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": meta.id,
        "title": meta.title,
        "uploader": meta.uploader,
        "uploader_id": meta.uploader_id,
        "channel": meta.channel,
        "channel_id": meta.channel_id,
        "duration": meta.duration,
        "upload_date": meta.upload_date,
        "thumbnail": meta.thumbnail,
        "chapter_count": meta.chapter_count,
        "webpage_url": meta.webpage_url,
    }
