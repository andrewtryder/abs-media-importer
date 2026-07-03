"""Route registration and shared dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def register_routers(app: FastAPI) -> None:
    from app.routes import config, diagnostics, extension, jobs, pages, ws

    app.include_router(config.router)
    app.include_router(jobs.router)
    app.include_router(jobs.abs_router)
    app.include_router(pages.router)
    app.include_router(diagnostics.router)
    app.include_router(extension.router)
    app.include_router(ws.router)
