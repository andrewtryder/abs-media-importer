"""Shared validation helpers for settings and per-job import options."""

from __future__ import annotations

import re
import shlex

from app.path_checks import check_readable_file, parse_absolute_file_path

ValidationResult = tuple[str | None, str | None]  # (error, warning)

_SHELL_INJECTION_RE = re.compile(r"[;|&`><]|&&|\|\||\$\(")
_AUDIO_BITRATE_RE = re.compile(r"^\d+k$", re.IGNORECASE)


def validate_optional_path(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return None, None
    path = parse_absolute_file_path(stripped)
    if path is None:
        return "Path must be absolute.", None
    return check_readable_file(path)


def validate_extra_args(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return None, None
    if _SHELL_INJECTION_RE.search(stripped):
        return "Arguments must not contain shell metacharacters (; | & ` > < && || $( ).", None
    warnings: list[str] = []
    try:
        tokens = shlex.split(stripped)
    except ValueError as exc:
        return f"Could not parse arguments: {exc}", None
    for token in tokens:
        if not token.startswith("-"):
            warnings.append(f'Unusual token "{token}" does not look like a flag.')
    warning = " ".join(warnings) if warnings else None
    return None, warning


def validate_filename_template(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return "Filename template cannot be empty.", None
    if ".." in stripped or "/" in stripped or "\\" in stripped:
        return "Template must not contain path separators.", None
    return None, None


def validate_lufs_target(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return "Loudness target cannot be empty.", None
    try:
        parsed = float(stripped)
    except ValueError:
        return "Must be a number (LUFS, typically negative).", None
    if parsed > 0:
        return "LUFS target must be zero or negative.", None
    if parsed < -70:
        return "LUFS target must be -70 or higher.", None
    return None, None


def validate_audio_bitrate(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return "Audio bitrate cannot be empty.", None
    if _AUDIO_BITRATE_RE.match(stripped):
        return None, None
    if stripped.isdigit():
        return None, None
    return 'Must be digits followed by "k" (e.g. 192k) or a plain integer bitrate.', None
