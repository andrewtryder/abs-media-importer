"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import os
import tomllib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib import request as urllib_request

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import attach_basic_auth
from app.config import get_settings
from app.db import init_db
from app.routes import register_routers
from app.routes.pages import STATIC_DIR, configure_templates

logger = logging.getLogger(__name__)


def _package_version() -> str:
    """Return the installed package version from pyproject.toml metadata."""
    try:
        return version("abs-media-importer")
    except PackageNotFoundError:
        data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
        return str(data["project"]["version"])


def _resolve_ui_version(default_version: str) -> str:
    """Resolve UI version from env override or latest GitHub release."""
    env_version = os.getenv("ABS_MEDIA_IMPORTER_UI_VERSION", "").strip()
    if env_version:
        return env_version

    fallback = default_version if default_version.startswith("v") else f"v{default_version}"
    repo = os.getenv("ABS_MEDIA_IMPORTER_GITHUB_REPO", "andrewtryder/abs-media-importer").strip()
    if "/" not in repo:
        return fallback

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib_request.Request(  # noqa: S310
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "abs-media-importer",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=2.5) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        tag = payload.get("tag_name") or payload.get("name")
        if isinstance(tag, str) and tag.strip():
            return tag.strip()
    except Exception:
        logger.debug("Could not resolve latest GitHub release version", exc_info=True)

    return fallback


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize DB on startup."""
    await init_db()
    logger.info("Database initialized")
    yield


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
    configure_templates(ui_version)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    if settings.auth_enabled:
        attach_basic_auth(app, settings)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    register_routers(app)
    return app
