"""Diagnostics checks for the doctor page and API."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from redis import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.path_checks import check_writable_directory
from app.services.audiobookshelf import AudiobookshelfClient

logger = logging.getLogger(__name__)

DiagnosticStatus = Literal["ok", "warn", "error", "skipped"]

_BINARY_TIMEOUT_SECONDS = 10
_REDIS_CONNECT_TIMEOUT_SECONDS = 3


@dataclass(frozen=True)
class DiagnosticCheck:
    id: str
    label: str
    status: DiagnosticStatus
    summary: str
    detail: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_free_space(path: str | Path | None) -> str:
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


def _first_output_line(result: subprocess.CompletedProcess[str]) -> str | None:
    for stream in (result.stdout, result.stderr):
        if stream:
            line = stream.strip().splitlines()[0].strip()
            if line:
                return line
    return None


def check_binary_version(
    *,
    check_id: str,
    label: str,
    binary: str,
    version_args: list[str],
) -> DiagnosticCheck:
    try:
        result = subprocess.run(
            [binary, *version_args],
            capture_output=True,
            text=True,
            timeout=_BINARY_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return DiagnosticCheck(
            id=check_id,
            label=label,
            status="error",
            summary="Binary not found",
            detail=f"Could not execute: {binary}",
        )
    except subprocess.TimeoutExpired:
        return DiagnosticCheck(
            id=check_id,
            label=label,
            status="error",
            summary="Version check timed out",
            detail=binary,
        )

    if result.returncode != 0:
        detail = _first_output_line(result) or f"Exit code {result.returncode}"
        return DiagnosticCheck(
            id=check_id,
            label=label,
            status="error",
            summary="Version check failed",
            detail=detail,
        )

    version_line = _first_output_line(result)
    return DiagnosticCheck(
        id=check_id,
        label=label,
        status="ok",
        summary="Available",
        detail=version_line or binary,
    )


def check_redis(settings: Settings) -> DiagnosticCheck:
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_SECONDS,
        )
        client.ping()
    except RedisError as exc:
        return DiagnosticCheck(
            id="redis",
            label="Redis",
            status="error",
            summary="Connection failed",
            detail=str(exc),
        )

    return DiagnosticCheck(
        id="redis",
        label="Redis",
        status="ok",
        summary="Connected",
        detail=settings.redis_url,
    )


def _sqlite_db_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite"):
        return None

    parsed = urlparse(database_url)
    if not parsed.path or parsed.path == "/":
        return None

    raw_path = unquote(parsed.path)
    if raw_path.startswith("//") and (len(raw_path) < 3 or raw_path[2] != "/"):
        raw_path = raw_path[1:]
    elif raw_path.startswith("///"):
        raw_path = raw_path[2:]
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        # Handle sqlite:///C:/path on Windows-style URLs.
        return Path(raw_path[1:])
    return Path(raw_path)


def check_database(settings: Settings) -> DiagnosticCheck:
    db_path = _sqlite_db_path(settings.sync_database_url)
    if db_path is None:
        return DiagnosticCheck(
            id="database",
            label="Database",
            status="warn",
            summary="Non-SQLite database URL",
            detail=settings.database_url,
        )

    parent_error = check_writable_directory(db_path.parent, create=True)
    exists = db_path.is_file()
    detail_parts = [f"File {'exists' if exists else 'will be created on first write'}"]
    if parent_error:
        return DiagnosticCheck(
            id="database",
            label="Database",
            status="error",
            summary="Database directory is not writable",
            detail=parent_error,
            path=str(db_path),
        )

    return DiagnosticCheck(
        id="database",
        label="Database",
        status="ok",
        summary="Writable",
        detail="; ".join(detail_parts),
        path=str(db_path),
    )


def check_path(
    *,
    check_id: str,
    label: str,
    path: Path,
    create: bool,
) -> DiagnosticCheck:
    error = check_writable_directory(path, create=create)
    free_space = format_free_space(path)
    detail = free_space if free_space != "N/A" else None

    if error:
        return DiagnosticCheck(
            id=check_id,
            label=label,
            status="error",
            summary="Not writable",
            detail=error if detail is None else f"{error}; {free_space}",
            path=str(path),
        )

    summary = "Writable"
    if detail:
        summary = f"Writable ({free_space})"

    return DiagnosticCheck(
        id=check_id,
        label=label,
        status="ok",
        summary=summary,
        detail=detail,
        path=str(path),
    )


def check_cookies(settings: Settings) -> DiagnosticCheck:
    cookies_file = settings.cookies_file
    if cookies_file is None:
        return DiagnosticCheck(
            id="cookies",
            label="Cookies file",
            status="warn",
            summary="Not configured",
            detail="Optional; required for some age-restricted or member-only videos",
        )

    path = Path(cookies_file)
    if not path.is_absolute():
        return DiagnosticCheck(
            id="cookies",
            label="Cookies file",
            status="error",
            summary="Path must be absolute",
            path=str(path),
        )
    if not path.exists():
        return DiagnosticCheck(
            id="cookies",
            label="Cookies file",
            status="error",
            summary="File does not exist",
            path=str(path),
        )
    if not path.is_file():
        return DiagnosticCheck(
            id="cookies",
            label="Cookies file",
            status="error",
            summary="Path is not a file",
            path=str(path),
        )
    if not os.access(path, os.R_OK):
        return DiagnosticCheck(
            id="cookies",
            label="Cookies file",
            status="error",
            summary="File is not readable",
            path=str(path),
        )

    return DiagnosticCheck(
        id="cookies",
        label="Cookies file",
        status="ok",
        summary="Present and readable",
        path=str(path),
    )


def check_abs_api(settings: Settings) -> DiagnosticCheck:
    client = AudiobookshelfClient(settings)
    result = client.check_connectivity()

    if result.skipped:
        return DiagnosticCheck(
            id="abs_api",
            label="Audiobookshelf API",
            status="skipped",
            summary="Not configured",
            detail=result.error,
        )
    if result.success:
        base_url = (settings.abs_base_url or "").rstrip("/")
        return DiagnosticCheck(
            id="abs_api",
            label="Audiobookshelf API",
            status="ok",
            summary="Connected",
            detail=base_url,
        )

    return DiagnosticCheck(
        id="abs_api",
        label="Audiobookshelf API",
        status="error",
        summary="Connection failed",
        detail=result.error,
    )


@dataclass(frozen=True)
class DiagnosticGroup:
    id: str
    label: str
    icon: str
    checks: tuple[DiagnosticCheck, ...]


_DIAGNOSTIC_GROUP_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("tools", "External tools", "build", ("ytdlp", "ffmpeg", "ffprobe")),
    ("infrastructure", "Infrastructure", "dns", ("redis", "database")),
    ("paths", "Paths & storage", "folder", ("output_root", "work_dir")),
    ("integrations", "Integrations", "hub", ("cookies", "abs_api")),
)


def diagnostic_groups(checks: list[DiagnosticCheck]) -> list[DiagnosticGroup]:
    by_id = {check.id: check for check in checks}
    return [
        DiagnosticGroup(
            id=group_id,
            label=label,
            icon=icon,
            checks=tuple(by_id[check_id] for check_id in check_ids),
        )
        for group_id, label, icon, check_ids in _DIAGNOSTIC_GROUP_SPECS
    ]


def run_diagnostics(settings: Settings) -> list[DiagnosticCheck]:
    """Run all diagnostics checks and return structured results."""
    return [
        check_binary_version(
            check_id="ytdlp",
            label="yt-dlp",
            binary=settings.ytdlp_bin,
            version_args=["--version"],
        ),
        check_binary_version(
            check_id="ffmpeg",
            label="ffmpeg",
            binary=settings.ffmpeg_bin,
            version_args=["-version"],
        ),
        check_binary_version(
            check_id="ffprobe",
            label="ffprobe",
            binary=settings.ffprobe_bin,
            version_args=["-version"],
        ),
        check_redis(settings),
        check_database(settings),
        check_path(
            check_id="output_root",
            label="Output root",
            path=settings.output_root,
            create=False,
        ),
        check_path(
            check_id="work_dir",
            label="Work directory",
            path=settings.work_dir,
            create=True,
        ),
        check_cookies(settings),
        check_abs_api(settings),
    ]
