"""Shared filesystem path validation helpers."""

from __future__ import annotations

import errno
import os
from pathlib import Path

ValidationResult = tuple[str | None, str | None]


def _format_os_error(path: Path, exc: OSError, *, create: bool) -> str:
    if exc.errno == errno.ENOENT:
        if not create:
            return f"Path does not exist or the bind mount is not available yet: {path}"
        return (
            f"Path is not writable: bind mount may not be ready yet ({path}). "
            f"Original error: {exc}"
        )
    return f"Path is not writable: {exc}"


def check_writable_directory(path: Path, *, create: bool = True) -> str | None:
    """Return an error message if *path* is not an absolute writable directory."""
    if not path.is_absolute():
        return "Path must be absolute."

    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        elif not path.is_dir():
            return f"Path does not exist or the bind mount is not available yet: {path}"

        test_file = path / ".write_test"
        test_file.touch()
        test_file.unlink()
    except OSError as exc:
        return _format_os_error(path, exc, create=create)

    return None


def parse_absolute_file_path(value: str) -> Path | None:
    """Parse *value* as an absolute path without touching the filesystem."""
    stripped = value.strip()
    if not stripped or "\0" in stripped:
        return None
    path = Path(stripped)
    if not path.is_absolute() or ".." in path.parts:
        return None
    return path


def check_readable_file(path: Path) -> ValidationResult:
    """Return (error, warning) for a structurally validated absolute file path."""
    resolved = path.resolve(strict=False)
    normalized = os.path.normpath(str(resolved))
    if not resolved.is_absolute() or not normalized.startswith(path.anchor):
        return "Path must be absolute.", None

    safe_path = Path(normalized)
    if not safe_path.exists():
        return None, "File does not exist yet; yt-dlp will fail until it is created."
    if not safe_path.is_file():
        return "Path must point to a file.", None
    if not os.access(safe_path, os.R_OK):
        return "File is not readable.", None
    return None, None
