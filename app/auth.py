"""Authentication middleware and dependencies."""

from __future__ import annotations

import base64
import contextlib
import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import Settings, get_settings


def extension_api_auth(
    request: Request, cfg: Annotated[Settings, Depends(get_settings)]
) -> Settings:
    """Check if extension API is enabled and authorized.

    Returns the settings object if access is permitted. Raises HTTPException
    with 404 if disabled, 401 if the token is missing/wrong.
    """
    if not cfg.extension_api_enabled:
        raise HTTPException(status_code=404, detail="Extension API not enabled")

    if cfg.extension_api_token:
        # Authorization: Bearer <token> or X-ABS-MEDIA-IMPORTER-Token header
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        x_token = request.headers.get("X-ABS-MEDIA-IMPORTER-Token")
        if x_token:
            token = x_token

        if not token or not secrets.compare_digest(token, cfg.extension_api_token):
            raise HTTPException(status_code=401, detail="Invalid extension API token")

    return cfg


ExtensionAuthDep = Annotated[Settings, Depends(extension_api_auth)]


async def validate_websocket_token(
    job_id: str,
    websocket: WebSocket,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Validate extension API token for WebSocket authentication.

    Browser extension WebSocket clients cannot reliably set custom Authorization
    headers, so we support `?token=` in addition to Bearer and X-ABS-MEDIA-IMPORTER-Token.
    """
    if not settings.extension_api_enabled:
        raise HTTPException(status_code=404, detail="Extension API not enabled")

    if settings.extension_api_token:
        token = None
        auth_header = websocket.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        x_token = websocket.headers.get("X-ABS-MEDIA-IMPORTER-Token")
        if x_token:
            token = x_token
        query_token = websocket.query_params.get("token")
        if query_token:
            token = query_token

        if not token or not secrets.compare_digest(token, settings.extension_api_token):
            raise HTTPException(status_code=401, detail="Invalid extension API token")


def attach_basic_auth(app: FastAPI, settings: Settings) -> None:
    """Add HTTP Basic Auth middleware."""
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
                headers={"WWW-Authenticate": 'Basic realm="abs-media-importer"'},
            )

    app.add_middleware(BasicAuthMiddleware)
