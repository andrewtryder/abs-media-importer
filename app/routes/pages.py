"""HTML page routes and Jinja2 template setup."""

from __future__ import annotations

import html
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings, save_custom_settings
from app.routes import DbDep, SettingsDep
from app.services.filesystem import FilesystemService
from app.services.jobs import (
    DuplicateVideoError,
    InvalidJobUrlError,
    JobSubmitParams,
    get_job,
    get_recent_jobs,
    submit_job,
)
from app.services.ytdlp import YtDlpService

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "--:--"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_date(date_str: str | None) -> str:
    """Format YYYYMMDD → YYYY-MM-DD."""
    if not date_str or len(date_str) != 8:
        return date_str or ""
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


def _escape_html(text: str | None) -> str:
    return html.escape(text or "")


def _format_free_space(path: str | Path | None) -> str:
    """Return free space label in MB/GB for the given path."""
    if path is None:
        return "N/A"

    probe = Path(path)
    candidates = [probe, probe.parent, Path("/")]
    for candidate in candidates:
        try:
            usage = shutil.disk_usage(candidate)
            free_bytes = usage.free
            gib = 1024**3
            mib = 1024**2
            if free_bytes >= gib:
                return f"{free_bytes / gib:.1f} GB free"
            return f"{free_bytes / mib:.0f} MB free"
        except OSError:
            logger.debug("Could not determine free disk space for %s", candidate, exc_info=True)
    return "N/A"


templates.env.filters["duration"] = _format_duration
templates.env.filters["format_date"] = _format_date
templates.env.filters["escape_html"] = _escape_html
templates.env.globals["format_free_space"] = _format_free_space


def configure_templates(ui_version: str) -> None:
    templates.env.globals["app_ui_version"] = ui_version


router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def page_home(request: Request, cfg: SettingsDep) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "settings": cfg},
    )


@router.post("/preview", response_class=HTMLResponse)
async def page_preview(
    request: Request,
    cfg: SettingsDep,
    url: str = Form(...),
) -> HTMLResponse:
    svc = YtDlpService(cfg)
    validation = svc.validate_url(url)
    if not validation.valid:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "settings": cfg,
                "error": validation.error,
                "url": url,
            },
            status_code=400,
        )
    try:
        meta = svc.run_preview(url)
    except Exception as exc:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "settings": cfg,
                "error": str(exc),
                "url": url,
            },
            status_code=422,
        )

    fs = FilesystemService(cfg)
    folders = fs.list_folders()

    return templates.TemplateResponse(
        "preview.html",
        {
            "request": request,
            "settings": cfg,
            "meta": meta,
            "folders": folders,
            "url": url,
            "default_folder": cfg.default_destination_folder or "",
        },
    )


@router.post("/jobs/create", response_class=HTMLResponse, response_model=None)
async def page_create_job(
    request: Request,
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
) -> HTMLResponse | RedirectResponse:
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
        job, _rq_id = await submit_job(db, cfg, params)
    except InvalidJobUrlError as exc:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "settings": cfg, "error": exc.error},
            status_code=400,
        )
    except DuplicateVideoError as exc:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "settings": cfg, "error": str(exc)},
            status_code=409,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "settings": cfg, "error": str(exc)},
            status_code=400,
        )

    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@router.get("/jobs", response_class=HTMLResponse)
async def page_jobs(request: Request, db: DbDep, cfg: SettingsDep) -> HTMLResponse:
    jobs = await get_recent_jobs(db)
    return templates.TemplateResponse(
        "jobs.html",
        {"request": request, "settings": cfg, "jobs": jobs},
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def page_job_detail(
    request: Request, job_id: str, db: DbDep, cfg: SettingsDep
) -> HTMLResponse:
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    fs = FilesystemService(cfg)
    log_path = fs.log_path(job_id)
    log_content = ""
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8", errors="replace")

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "settings": cfg,
            "job": job,
            "log": log_content,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request, cfg: SettingsDep) -> HTMLResponse:
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": cfg,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def page_update_settings(
    request: Request,
    cfg: SettingsDep,
    output_root: str = Form(...),
    dry_run: bool = Form(False),
    allow_playlists: bool = Form(False),
    allow_channels: bool = Form(False),
    abs_scan_after_success: bool = Form(False),
) -> HTMLResponse:
    p = Path(output_root.strip())
    error = None
    if not p.is_absolute():
        error = "Output root directory must be an absolute path."
    else:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / f".write_test_{uuid.uuid4()}"
            test_file.touch()
            test_file.unlink()
        except Exception as exc:
            error = f"Output root is not writable: {exc}"

    if error:
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings": cfg,
                "error": error,
                "output_root": output_root,
                "form_values": {
                    "dry_run": dry_run,
                    "allow_playlists": allow_playlists,
                    "allow_channels": allow_channels,
                    "abs_scan_after_success": abs_scan_after_success,
                },
            },
            status_code=400,
        )

    save_custom_settings(
        output_root,
        dry_run=dry_run,
        allow_playlists=allow_playlists,
        allow_channels=allow_channels,
        abs_scan_after_success=abs_scan_after_success,
    )
    new_cfg = get_settings()

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": new_cfg,
            "success": "Settings saved successfully and reloaded.",
        },
    )
