"""HTML page routes and Jinja2 template setup."""

from __future__ import annotations

import html
import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_setting_sources, reload_settings, save_settings
from app.diagnostics import format_free_space
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
from app.settings_registry import (
    parse_form_value,
    registry_groups,
)

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


templates.env.filters["duration"] = _format_duration
templates.env.filters["format_date"] = _format_date
templates.env.filters["escape_html"] = _escape_html
templates.env.globals["format_free_space"] = format_free_space


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


def _build_settings_context(
    request: Request,
    cfg: Settings,
    *,
    form_values: dict[str, str] | None = None,
    field_errors: dict[str, str] | None = None,
    field_warnings: dict[str, str] | None = None,
    error: str | None = None,
    success: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    sources = get_setting_sources()
    groups: list[dict[str, object]] = []
    for group_id, group_label, specs in registry_groups():
        fields: list[dict[str, object]] = []
        for spec in specs:
            meta = sources[spec.key]
            value = form_values.get(spec.key, meta["value"]) if form_values else meta["value"]
            fields.append(
                {
                    "spec": spec,
                    "value": value,
                    "source": meta["source"],
                    "locked": meta["locked"],
                    "restart_required": meta["restart_required"],
                    "error": (field_errors or {}).get(spec.key),
                    "warning": (field_warnings or {}).get(spec.key),
                }
            )
        groups.append({"id": group_id, "label": group_label, "fields": fields})
    return {
        "request": request,
        "settings": cfg,
        "setting_groups": groups,
        "error": error,
        "success": success,
        "warnings": warnings or [],
    }


def _process_settings_form(
    form: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], list[str]]:
    """Validate submitted settings form; return overrides, errors, warnings, global warnings."""
    from app.settings_registry import SETTINGS_REGISTRY

    sources = get_setting_sources()
    overrides: dict[str, str] = {}
    errors: dict[str, str] = {}
    warnings: dict[str, str] = {}
    global_warnings: list[str] = []

    for spec in SETTINGS_REGISTRY:
        if not spec.mutable or sources[spec.key]["locked"]:
            continue
        raw = form.get(spec.key)
        value = parse_form_value(raw, spec)
        if spec.validate:
            error, warning = spec.validate(value)
            if error:
                errors[spec.key] = error
                continue
            if warning:
                warnings[spec.key] = warning
        overrides[spec.key] = value
        if spec.restart_required:
            global_warnings.append(
                f"{spec.label} may require a process restart to take full effect."
            )

    return overrides, errors, warnings, global_warnings


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request, cfg: SettingsDep) -> HTMLResponse:
    return templates.TemplateResponse(
        "settings.html",
        _build_settings_context(request, cfg),
    )


@router.post("/settings", response_class=HTMLResponse)
async def page_update_settings(request: Request, cfg: SettingsDep) -> HTMLResponse:
    form = {
        key: value for key, value in (await request.form()).multi_items() if isinstance(value, str)
    }
    overrides, field_errors, field_warnings, global_warnings = _process_settings_form(form)

    if field_errors:
        from app.settings_registry import SETTINGS_REGISTRY

        form_values = {
            spec.key: parse_form_value(form.get(spec.key), spec) for spec in SETTINGS_REGISTRY
        }
        return templates.TemplateResponse(
            "settings.html",
            _build_settings_context(
                request,
                cfg,
                form_values=form_values,
                field_errors=field_errors,
                field_warnings=field_warnings,
                error="Please fix the highlighted settings before saving.",
            ),
            status_code=400,
        )

    save_settings(overrides)
    new_cfg = reload_settings()

    return templates.TemplateResponse(
        "settings.html",
        _build_settings_context(
            request,
            new_cfg,
            field_warnings=field_warnings,
            success="Settings saved successfully and reloaded.",
            warnings=global_warnings,
        ),
    )
