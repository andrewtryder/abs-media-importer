"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import os
import tomllib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

from app.auth import attach_basic_auth
from app.config import get_settings, reload_settings
from app.db import init_db
from app.preflight import check_required_paths
from app.routes import register_routers
from app.routes.pages import STATIC_DIR, configure_templates

logger = logging.getLogger(__name__)

_GITHUB_RELEASE_TIMEOUT_SECONDS = 2.5


def _package_version() -> str:
    """Return the installed package version from pyproject.toml metadata."""
    try:
        return version("abs-media-importer")
    except PackageNotFoundError:
        data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
        return str(data["project"]["version"])


def _fallback_ui_version(default_version: str) -> str:
    """Return a v-prefixed package version for display."""
    return default_version if default_version.startswith("v") else f"v{default_version}"


def _ui_version_env_override() -> str | None:
    """Return ABS_MEDIA_IMPORTER_UI_VERSION when set, else None."""
    env_version = os.getenv("ABS_MEDIA_IMPORTER_UI_VERSION", "").strip()
    return env_version or None


def _background_ui_version_fetch_enabled() -> bool:
    """Return True when the GitHub release lookup should run in the background."""
    if _ui_version_env_override() is not None:
        return False
    # Tests set this to 0 so TestClient lifespan never schedules network work.
    flag = os.getenv("ABS_MEDIA_IMPORTER_FETCH_UI_VERSION", "1").strip().lower()
    return flag not in {"0", "false", "no"}


def _resolve_ui_version(default_version: str) -> str:
    """Resolve UI version from env override or package fallback (no network I/O)."""
    env_version = _ui_version_env_override()
    if env_version is not None:
        return env_version
    return _fallback_ui_version(default_version)


async def _fetch_latest_ui_version_async(fallback: str) -> str:
    """Fetch the latest GitHub release tag, returning *fallback* on any failure."""
    repo = os.getenv("ABS_MEDIA_IMPORTER_GITHUB_REPO", "andrewtryder/abs-media-importer").strip()
    if "/" not in repo:
        return fallback

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_GITHUB_RELEASE_TIMEOUT_SECONDS) as client:
            response = await client.get(
                api_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "abs-media-importer",
                },
            )
            response.raise_for_status()
            payload = response.json()
        tag = payload.get("tag_name") or payload.get("name")
        if isinstance(tag, str) and tag.strip():
            return tag.strip()
    except Exception:
        logger.debug("Could not resolve latest GitHub release version", exc_info=True)

    return fallback


async def _refresh_ui_version(app: FastAPI) -> None:
    """Update app.state and template globals once the latest release is known."""
    fallback = app.state.ui_version
    resolved = await _fetch_latest_ui_version_async(fallback)
    app.state.ui_version = resolved
    configure_templates(resolved)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize DB on startup; resolve UI version in the background."""
    await init_db()
    reload_settings()
    logger.info("Database initialized")

    # Env override / test flag is applied in create_app; only hit GitHub when enabled.
    if _background_ui_version_fetch_enabled():
        app.state.ui_version_task = asyncio.create_task(_refresh_ui_version(app))
    else:
        app.state.ui_version_task = None

    yield

    # Cancel only — do not await. Awaiting can deadlock Starlette's TestClient
    # portal when the task is mid-I/O during lifespan shutdown.
    task = getattr(app.state, "ui_version_task", None)
    if task is not None and not task.done():
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="abs-media-importer",
        description="Selective YouTube → Audiobookshelf importer",
        version=_package_version(),
        lifespan=lifespan,
    )
    ui_version = _resolve_ui_version(app.version)
    app.state.ui_version = ui_version
    app.state.ui_version_task = None
    configure_templates(ui_version)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    if settings.auth_enabled:
        attach_basic_auth(app, settings)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        results = check_required_paths()
        checks = {
            result.name.lower(): {
                "path": str(result.path),
                "ok": result.error is None,
                **({"error": result.error} if result.error else {}),
            }
            for result in results
        }
        all_ok = all(result.error is None for result in results)
        return JSONResponse(
            content={"status": "ready" if all_ok else "not_ready", "checks": checks},
            status_code=200 if all_ok else 503,
        )

    register_routers(app)
    return app
