"""FastAPI application: routes, middleware, and startup."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings, save_custom_settings
from app.db import get_db, init_db
from app.models import Job, JobStatus
from app.queue import enqueue_job_task
from app.services.audiobookshelf import AudiobookshelfClient
from app.services.filesystem import FilesystemService
from app.services.jobs import (
    create_job,
    get_job,
    get_recent_jobs,
    update_job_status,
)
from app.services.ytdlp import YtDlpService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Templates directory
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Register custom Jinja2 filters
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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize DB on startup."""
    await init_db()
    logger.info("Database initialized")
    yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="yt-abs-importer",
        description="Selective YouTube → Audiobookshelf importer",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Auth middleware
    if settings.auth_enabled:
        _attach_basic_auth(app, settings)

    _register_routes(app, settings)
    return app


def _attach_basic_auth(app: FastAPI, settings: Settings) -> None:
    """Add HTTP Basic Auth middleware."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    expected_user = settings.auth_username or ""
    expected_pass = settings.auth_password or ""

    class BasicAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self,
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            # Skip health endpoint
            if request.url.path == "/health":
                return await call_next(request)

            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Basic "):
                with contextlib.suppress(Exception):
                    decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                    user, _, pwd = decoded.partition(":")
                    if secrets.compare_digest(user, expected_user) and secrets.compare_digest(
                        pwd, expected_pass
                    ):
                        return await call_next(request)

            return Response(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="yt-abs-importer"'},
            )

    app.add_middleware(BasicAuthMiddleware)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _extension_api_auth(request: Request, cfg: SettingsDep) -> Settings:
    """Check if extension API is enabled and authorized.

    Returns the settings object if access is permitted. Raises HTTPException
    with 404 if disabled, 401 if the token is missing/wrong.
    """
    if not cfg.extension_api_enabled:
        raise HTTPException(status_code=404, detail="Extension API not enabled")

    if cfg.extension_api_token:
        # Authorization: Bearer <token> or X-YTABS-Token header
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        x_token = request.headers.get("X-YTABS-Token")
        if x_token:
            token = x_token

        if not token or not secrets.compare_digest(token, cfg.extension_api_token):
            raise HTTPException(status_code=401, detail="Invalid extension API token")

    return cfg


ExtensionAuthDep = Annotated[Settings, Depends(_extension_api_auth)]


async def _validate_websocket_token(job_id: str, request: Request, settings: SettingsDep) -> None:
    """Validate extension API token for WebSocket authentication."""
    if not settings.extension_api_enabled:
        raise HTTPException(status_code=404, detail="Extension API not enabled")

    if settings.extension_api_token:
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        x_token = request.headers.get("X-YTABS-Token")
        if x_token:
            token = x_token

        if not token or not secrets.compare_digest(token, settings.extension_api_token):
            raise HTTPException(status_code=401, detail="Invalid extension API token")


async def _websocket_endpoint(
    websocket: WebSocket,
    job_id: str,
    request: Request,
    cfg: SettingsDep,
    db: AsyncSession,
) -> None:
    """WebSocket endpoint for real-time job status updates."""
    await websocket.accept()

    # Validate token authentication
    try:
        await _validate_websocket_token(job_id, request, cfg)
    except HTTPException as e:
        if e.status_code == 404:
            await websocket.close(code=1008)
        else:
            await websocket.close(code=1008, reason=e.detail)
        return

    # Validate job exists
    job = await get_job(db, job_id)
    if not job:
        await websocket.close(code=1008, reason="Job not found")
        return

    # Initial snapshot
    await websocket.send_json({"type": "job_update", "job": _job_dict(job)})

    # WebSocket polling loop
    try:
        last_data = _job_dict(job)
        while True:
            # Get current job state
            current_job = await get_job(db, job_id)
            if not current_job:
                await websocket.close(code=1000, reason="Job no longer exists")
                return

            current_data = _job_dict(current_job)

            # Check for meaningful changes (fields that trigger UI updates)
            meaningful_changes = False
            fields_to_check = [
                "status",
                "phase",
                "progress",
                "progress_percent",
                "progress_label",
                "progress_eta",
                "progress_speed",
                "error_message",
                "final_output_path",
            ]

            for field in fields_to_check:
                if last_data.get(field) != current_data.get(field):
                    meaningful_changes = True
                    break

            if meaningful_changes:
                await websocket.send_json({"type": "job_update", "job": current_data})
                last_data = current_data

            # Check for terminal status
            if current_job.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                await websocket.send_json({"type": "job_update", "job": current_data})
                break

            # Wait before next poll
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for job %s", job_id)
    except Exception:
        logger.exception("Unexpected WebSocket error for job %s", job_id)
    finally:
        await websocket.close(code=1000)


def _register_routes(app: FastAPI, settings: Settings) -> None:
    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Config API ────────────────────────────────────────────────────────────

    @app.get("/api/config")
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

    # ── Folder API ────────────────────────────────────────────────────────────

    @app.get("/api/folders")
    async def api_folders(cfg: SettingsDep) -> dict[str, list[str]]:
        fs = FilesystemService(cfg)
        return {"folders": fs.list_folders()}

    # ── Preview API ───────────────────────────────────────────────────────────

    @app.post("/api/preview")
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

    # ── Jobs API ──────────────────────────────────────────────────────────────

    @app.get("/api/jobs")
    async def api_list_jobs(db: DbDep) -> dict[str, Any]:
        jobs = await get_recent_jobs(db)
        return {"jobs": [_job_dict(j) for j in jobs]}

    @app.post("/api/jobs", status_code=201)
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
    ) -> JSONResponse:
        svc = YtDlpService(cfg)
        validation = svc.validate_url(url)
        if not validation.valid:
            raise HTTPException(status_code=400, detail=validation.error)

        # Create new folder if requested
        fs = FilesystemService(cfg)
        if new_folder.strip():
            try:
                fs.create_folder(new_folder.strip())
                destination_folder = new_folder.strip()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        job = await create_job(
            db,
            url,
            cfg,
            video_id=video_id or None,
            source_title=source_title or None,
            uploader=uploader or None,
            uploader_id=uploader_id or None,
            channel=channel or None,
            channel_id=channel_id or None,
            duration=duration or None,
            upload_date=upload_date or None,
            thumbnail_url=thumbnail_url or None,
            chapter_count=chapter_count or None,
            output_title=output_title or source_title or None,
            destination_folder=destination_folder or None,
            embed_metadata=embed_metadata,
            embed_thumbnail=embed_thumbnail,
            embed_chapters=embed_chapters,
            trigger_abs_scan=trigger_abs_scan,
        )

        rq_id = enqueue_job_task(job.id)
        await update_job_status(db, job.id, JobStatus.queued, rq_job_id=rq_id)

        return JSONResponse({"job_id": job.id, "rq_job_id": rq_id}, status_code=201)

    @app.get("/api/jobs/{job_id}")
    async def api_get_job(job_id: str, db: DbDep) -> dict[str, Any]:
        job = await get_job(db, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_dict(job)

    @app.get("/api/jobs/{job_id}/log")
    async def api_get_log(job_id: str, db: DbDep, cfg: SettingsDep) -> dict[str, str]:
        job = await get_job(db, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        fs = FilesystemService(cfg)
        log_path = fs.log_path(job_id)
        if not log_path.exists():
            return {"log": ""}
        return {"log": log_path.read_text(encoding="utf-8", errors="replace")}

    @app.post("/api/jobs/{job_id}/retry")
    async def api_retry_job(job_id: str, db: DbDep, cfg: SettingsDep) -> dict[str, str]:
        job = await get_job(db, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status not in {JobStatus.failed, JobStatus.cancelled}:
            raise HTTPException(
                status_code=409,
                detail=f"Job status is '{job.status}', can only retry failed/cancelled jobs",
            )
        # Reset for retry
        await update_job_status(db, job_id, JobStatus.queued, phase="queued", error_message="")
        rq_id = enqueue_job_task(job_id)
        await update_job_status(db, job_id, JobStatus.queued, rq_job_id=rq_id)
        return {"job_id": job_id, "rq_job_id": rq_id, "status": "queued"}

    @app.post("/api/jobs/{job_id}/cancel")
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

    @app.post("/api/audiobookshelf/scan")
    async def api_abs_scan(cfg: SettingsDep) -> dict[str, Any]:
        client = AudiobookshelfClient(cfg)
        result = client.trigger_scan()
        return {
            "success": result.success,
            "skipped": result.skipped,
            "error": result.error,
        }

    # ── HTML Pages ─────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def page_home(request: Request, cfg: SettingsDep) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "settings": cfg},
        )

    @app.post("/preview", response_class=HTMLResponse)
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

    @app.post("/jobs/create", response_class=HTMLResponse, response_model=None)
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
    ) -> HTMLResponse | RedirectResponse:
        svc = YtDlpService(cfg)
        validation = svc.validate_url(url)
        if not validation.valid:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "settings": cfg, "error": validation.error},
                status_code=400,
            )

        fs = FilesystemService(cfg)
        if new_folder.strip():
            try:
                fs.create_folder(new_folder.strip())
                destination_folder = new_folder.strip()
            except ValueError as exc:
                return templates.TemplateResponse(
                    "index.html",
                    {"request": request, "settings": cfg, "error": str(exc)},
                    status_code=400,
                )

        job = await create_job(
            db,
            url,
            cfg,
            video_id=video_id or None,
            source_title=source_title or None,
            uploader=uploader or None,
            uploader_id=uploader_id or None,
            channel=channel or None,
            channel_id=channel_id or None,
            duration=duration or None,
            upload_date=upload_date or None,
            thumbnail_url=thumbnail_url or None,
            chapter_count=chapter_count or None,
            output_title=output_title or source_title or None,
            destination_folder=destination_folder or None,
            embed_metadata=embed_metadata,
            embed_thumbnail=embed_thumbnail,
            embed_chapters=embed_chapters,
            trigger_abs_scan=trigger_abs_scan,
        )

        rq_id = enqueue_job_task(job.id)
        await update_job_status(db, job.id, JobStatus.queued, rq_job_id=rq_id)

        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/jobs", response_class=HTMLResponse)
    async def page_jobs(request: Request, db: DbDep, cfg: SettingsDep) -> HTMLResponse:
        jobs = await get_recent_jobs(db)
        return templates.TemplateResponse(
            "jobs.html",
            {"request": request, "settings": cfg, "jobs": jobs},
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
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

    @app.get("/settings", response_class=HTMLResponse)
    async def page_settings(request: Request, cfg: SettingsDep) -> HTMLResponse:
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings": cfg,
            },
        )

    @app.post("/settings", response_class=HTMLResponse)
    async def page_update_settings(
        request: Request,
        cfg: SettingsDep,
        output_root: str = Form(...),
    ) -> HTMLResponse:
        import uuid

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
                },
                status_code=400,
            )

        save_custom_settings(output_root)
        new_cfg = get_settings()

        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings": new_cfg,
                "success": "Settings saved successfully and reloaded.",
            },
        )

    # ── Extension API ────────────────────────────────────────────────────────────

    @app.websocket("/api/ws/jobs/{job_id}")
    async def api_websocket_job_status(
        websocket: WebSocket,
        job_id: str,
        request: Request,
        cfg: SettingsDep,
        db: DbDep,
    ) -> None:
        """WebSocket endpoint for real-time job status updates."""
        await _websocket_endpoint(websocket, job_id, request, cfg, db)

    @app.get("/api/extension/status")
    async def api_extension_status(cfg: ExtensionAuthDep) -> dict[str, Any]:
        # Return a subset of settings that is safe to expose
        return {
            "ok": True,
            "app": "yt-abs-importer",
            "extension_api_enabled": cfg.extension_api_enabled,
            "auth_required": bool(cfg.extension_api_token),
            "dry_run": cfg.dry_run,
            "abs_configured": cfg.abs_configured,
            "allow_playlists": cfg.allow_playlists,
            "allow_channels": cfg.allow_channels,
        }

    @app.post("/api/extension/queue", status_code=201)
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

        # Validate URL
        svc = YtDlpService(cfg)
        validation = svc.validate_url(url)
        if not validation.valid:
            raise HTTPException(status_code=400, detail=validation.error)

        # Fetch metadata
        try:
            meta = svc.run_preview(url)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Extract parameters
        destination_folder = data.get("destination_folder", "")
        output_title = data.get("output_title", "")
        embed_metadata = data.get("embed_metadata", True)
        embed_thumbnail = data.get("embed_thumbnail", True)
        embed_chapters = data.get("embed_chapters", True)
        trigger_abs_scan = data.get("trigger_abs_scan", False)

        # Create job
        job = await create_job(
            db,
            url,
            cfg,
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
        )

        # Enqueue task
        rq_id = enqueue_job_task(job.id)
        await update_job_status(db, job.id, JobStatus.queued, rq_job_id=rq_id)

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


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------


def _job_dict(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "url": job.url,
        "video_id": job.video_id,
        "source_title": job.source_title,
        "output_title": job.output_title,
        "destination_folder": job.destination_folder,
        "final_output_path": job.final_output_path,
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.app_host,
        port=s.app_port,
        reload=False,
    )
