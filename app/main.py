"""FastAPI application entry point."""

from __future__ import annotations

from app.config import get_settings
from app.factory import create_app

app = create_app()

__all__ = ["app", "create_app"]

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.app_host,
        port=s.app_port,
        reload=False,
    )
