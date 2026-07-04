"""WebSocket routes for real-time job updates."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.websockets import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import validate_websocket_token
from app.models import JobStatus
from app.routes import DbDep, SettingsDep
from app.serializers import job_dict
from app.services.jobs import get_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ws", tags=["websocket"])

_POLL_INTERVAL_SECONDS = 5.0


async def _websocket_endpoint(
    websocket: WebSocket,
    job_id: str,
    cfg: SettingsDep,
    db: AsyncSession,
) -> None:
    """WebSocket endpoint for real-time job status updates."""
    await websocket.accept()

    try:
        await validate_websocket_token(job_id, websocket, cfg)
    except HTTPException as e:
        if e.status_code == 404:
            await websocket.close(code=1008)
        else:
            await websocket.close(code=1008, reason=e.detail)
        return

    job = await get_job(db, job_id)
    if not job:
        await websocket.close(code=1008, reason="Job not found")
        return

    await websocket.send_json({"type": "job_update", "job": job_dict(job)})

    try:
        last_data = job_dict(job)
        while True:
            current_job = await get_job(db, job_id)
            if not current_job:
                await websocket.close(code=1000, reason="Job no longer exists")
                return

            current_data = job_dict(current_job)

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

            if current_job.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                await websocket.send_json({"type": "job_update", "job": current_data})
                break

            # Sleep is interruptible by task cancellation when the TestClient
            # portal tears down. Avoid websocket.receive() here: Starlette's
            # TestClient has a race between disconnect enqueue and receive wait
            # that can hang CI indefinitely.
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for job %s", job_id)
    except Exception:
        logger.exception("Unexpected WebSocket error for job %s", job_id)
    finally:
        with suppress(Exception):
            await websocket.close(code=1000)


@router.websocket("/jobs/{job_id}")
async def api_websocket_job_status(
    websocket: WebSocket,
    job_id: str,
    cfg: SettingsDep,
    db: DbDep,
) -> None:
    """WebSocket endpoint for real-time job status updates."""
    await _websocket_endpoint(websocket, job_id, cfg, db)
