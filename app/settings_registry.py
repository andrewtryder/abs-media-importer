"""Metadata-driven configuration registry for the Settings UI."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.path_checks import check_writable_directory

ValidationResult = tuple[str | None, str | None]  # (error, warning)

_SHELL_INJECTION_RE = re.compile(r"[;|&`><]|&&|\|\||\$\(")


class SettingType(StrEnum):
    BOOL = "bool"
    INT = "int"
    STR = "str"
    PATH = "path"
    ENUM = "enum"
    CSV_LIST = "csv_list"
    SPACE_LIST = "space_list"
    INT_LIST = "int_list"


@dataclass(frozen=True)
class SettingSpec:
    """Declarative metadata for a single application setting."""

    key: str
    env_alias: str
    label: str
    group: str
    type: SettingType
    default: Any
    help_text: str = ""
    choices: tuple[str, ...] = ()
    mutable: bool = True
    secret: bool = False
    restart_required: bool = False
    validate: Callable[[str], ValidationResult] | None = None
    show_in_ui: bool = True


def _validate_absolute_writable_path(value: str) -> ValidationResult:
    error = check_writable_directory(Path(value.strip()), create=True)
    if error:
        return error, None
    return None, None


def _validate_optional_path(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return None, None
    p = Path(stripped)
    if not p.is_absolute():
        return "Path must be absolute.", None
    if not p.exists():
        return None, "File does not exist yet; yt-dlp will fail until it is created."
    if not p.is_file():
        return "Path must point to a file.", None
    if not os.access(p, os.R_OK):
        return "File is not readable.", None
    return None, None


def _validate_extra_args(value: str) -> ValidationResult:
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


def _validate_positive_int(value: str) -> ValidationResult:
    try:
        parsed = int(value.strip())
    except ValueError:
        return "Must be a whole number.", None
    if parsed <= 0:
        return "Must be greater than zero.", None
    return None, None


def _validate_retry_max(value: str) -> ValidationResult:
    try:
        parsed = int(value.strip())
    except ValueError:
        return "Must be a whole number.", None
    if parsed < 0:
        return "Must be zero or greater.", None
    return None, None


def _validate_int_list(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return "At least one interval is required.", None
    try:
        values = [int(x.strip()) for x in stripped.split(",") if x.strip()]
    except ValueError:
        return "Must be comma-separated integers.", None
    if not values:
        return "At least one interval is required.", None
    if any(v <= 0 for v in values):
        return "All intervals must be greater than zero.", None
    return None, None


def _validate_filename_template(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return "Filename template cannot be empty.", None
    if ".." in stripped or "/" in stripped or "\\" in stripped:
        return "Template must not contain path separators.", None
    return None, None


COLLISION_CHOICES = ("skip", "overwrite", "append_id", "append_counter")

SETTINGS_REGISTRY: list[SettingSpec] = [
    # ── Paths ────────────────────────────────────────────────────────────────
    SettingSpec(
        key="output_root",
        env_alias="OUTPUT_ROOT",
        label="Output Root Directory",
        group="paths",
        type=SettingType.PATH,
        default="/media/podcasts",
        help_text="Base folder where finished audiobook files are written.",
        validate=_validate_absolute_writable_path,
    ),
    SettingSpec(
        key="default_destination_folder",
        env_alias="DEFAULT_DESTINATION_FOLDER",
        label="Default Destination Folder",
        group="paths",
        type=SettingType.STR,
        default="",
        help_text="Optional subdirectory under the output root selected by default in the UI.",
    ),
    SettingSpec(
        key="cookies_file",
        env_alias="COOKIES_FILE",
        label="YouTube Cookies File",
        group="paths",
        type=SettingType.PATH,
        default="",
        help_text="Absolute path to a Netscape-format cookies file for yt-dlp.",
        validate=_validate_optional_path,
    ),
    # ── Download behavior ────────────────────────────────────────────────────
    SettingSpec(
        key="collision_mode",
        env_alias="COLLISION_MODE",
        label="Collision Mode",
        group="download",
        type=SettingType.ENUM,
        default="append_id",
        choices=COLLISION_CHOICES,
        help_text="Strategy when the output file already exists.",
    ),
    SettingSpec(
        key="output_extension",
        env_alias="OUTPUT_EXTENSION",
        label="Output Extension",
        group="download",
        type=SettingType.STR,
        default="m4b",
        help_text="File extension for finished output (usually m4b).",
    ),
    SettingSpec(
        key="allowed_domains",
        env_alias="ALLOWED_DOMAINS",
        label="Allowed Domains",
        group="download",
        type=SettingType.CSV_LIST,
        default="youtube.com,www.youtube.com,m.youtube.com,music.youtube.com,youtu.be",
        help_text="Comma-separated hostnames permitted for import URLs.",
    ),
    SettingSpec(
        key="ytdlp_extra_args",
        env_alias="YTDLP_EXTRA_ARGS",
        label="yt-dlp Extra Arguments",
        group="download",
        type=SettingType.SPACE_LIST,
        default="",
        help_text="Space-separated extra arguments passed to yt-dlp.",
        validate=_validate_extra_args,
    ),
    SettingSpec(
        key="ffmpeg_extra_args",
        env_alias="FFMPEG_EXTRA_ARGS",
        label="ffmpeg Extra Arguments",
        group="download",
        type=SettingType.SPACE_LIST,
        default="",
        help_text="Space-separated extra arguments passed to ffmpeg.",
        validate=_validate_extra_args,
    ),
    # ── Naming ───────────────────────────────────────────────────────────────
    SettingSpec(
        key="filename_template",
        env_alias="FILENAME_TEMPLATE",
        label="Filename Template",
        group="naming",
        type=SettingType.STR,
        default="{title}.m4b",
        help_text="Template for the final output filename.",
        validate=_validate_filename_template,
    ),
    SettingSpec(
        key="folder_name_field",
        env_alias="FOLDER_NAME_FIELD",
        label="Folder Name Field",
        group="naming",
        type=SettingType.STR,
        default="uploader_id",
        help_text="Primary metadata field used for the output folder name.",
    ),
    SettingSpec(
        key="folder_name_fallbacks",
        env_alias="FOLDER_NAME_FALLBACKS",
        label="Folder Name Fallbacks",
        group="naming",
        type=SettingType.CSV_LIST,
        default="uploader_id,channel_id,channel,uploader",
        help_text="Comma-separated fallback fields for folder naming.",
    ),
    # ── Jobs ─────────────────────────────────────────────────────────────────
    SettingSpec(
        key="job_timeout_seconds",
        env_alias="JOB_TIMEOUT_SECONDS",
        label="Job Timeout (seconds)",
        group="jobs",
        type=SettingType.INT,
        default="10800",
        help_text="Maximum runtime for a single import job.",
        validate=_validate_positive_int,
        restart_required=True,
    ),
    SettingSpec(
        key="retry_max",
        env_alias="RETRY_MAX",
        label="Retry Count",
        group="jobs",
        type=SettingType.INT,
        default="3",
        help_text="Maximum number of retry attempts after failure.",
        validate=_validate_retry_max,
    ),
    SettingSpec(
        key="retry_interval_seconds",
        env_alias="RETRY_INTERVAL_SECONDS",
        label="Retry Intervals (seconds)",
        group="jobs",
        type=SettingType.INT_LIST,
        default="60,300,900",
        help_text="Comma-separated wait times between retries.",
        validate=_validate_int_list,
    ),
    SettingSpec(
        key="cleanup_temp_on_success",
        env_alias="CLEANUP_TEMP_ON_SUCCESS",
        label="Cleanup Temp on Success",
        group="jobs",
        type=SettingType.BOOL,
        default="true",
        help_text="Remove temporary working files after a successful import.",
    ),
    SettingSpec(
        key="cleanup_temp_on_failure",
        env_alias="CLEANUP_TEMP_ON_FAILURE",
        label="Cleanup Temp on Failure",
        group="jobs",
        type=SettingType.BOOL,
        default="false",
        help_text="Remove temporary working files after a failed import.",
    ),
    SettingSpec(
        key="max_concurrent_jobs",
        env_alias="MAX_CONCURRENT_JOBS",
        label="Max Concurrent Jobs",
        group="jobs",
        type=SettingType.INT,
        default="1",
        help_text="Maximum simultaneous imports (read-only until runtime supports tuning).",
        mutable=False,
        restart_required=True,
    ),
    # ── Runtime behavior ─────────────────────────────────────────────────────
    SettingSpec(
        key="dry_run",
        env_alias="DRY_RUN",
        label="Dry Run Mode",
        group="runtime",
        type=SettingType.BOOL,
        default="false",
        help_text="Build commands and write a fake output file only.",
    ),
    SettingSpec(
        key="allow_playlists",
        env_alias="ALLOW_PLAYLISTS",
        label="Allow Playlist URLs",
        group="runtime",
        type=SettingType.BOOL,
        default="false",
        help_text=(
            "Permit playlist-style URLs, but import only the selected/single "
            "video; full playlist batch imports are not yet supported."
        ),
    ),
    SettingSpec(
        key="allow_channels",
        env_alias="ALLOW_CHANNELS",
        label="Allow Channel URLs",
        group="runtime",
        type=SettingType.BOOL,
        default="false",
        help_text=(
            "Permit channel-style URLs where yt-dlp can resolve a single item; "
            "full channel batch imports are not yet supported."
        ),
    ),
    SettingSpec(
        key="abs_scan_after_success",
        env_alias="ABS_SCAN_AFTER_SUCCESS",
        label="Trigger ABS Scan After Success",
        group="runtime",
        type=SettingType.BOOL,
        default="false",
        help_text="Request an Audiobookshelf library scan after successful imports.",
    ),
]

SETTINGS_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SETTINGS_REGISTRY}

GROUP_LABELS: dict[str, str] = {
    "paths": "Paths & Files",
    "download": "Download & Processing",
    "naming": "Naming",
    "jobs": "Job Management",
    "runtime": "Runtime Behavior",
}

GROUP_ORDER: tuple[str, ...] = ("paths", "download", "naming", "jobs", "runtime")


def registry_groups() -> list[tuple[str, str, list[SettingSpec]]]:
    """Return registry entries grouped for UI rendering."""
    grouped: dict[str, list[SettingSpec]] = {group: [] for group in GROUP_ORDER}
    for spec in SETTINGS_REGISTRY:
        if spec.show_in_ui:
            grouped.setdefault(spec.group, []).append(spec)
    return [
        (group, GROUP_LABELS.get(group, group.title()), grouped[group])
        for group in GROUP_ORDER
        if grouped.get(group)
    ]


def format_setting_value(value: object, spec: SettingSpec) -> str:
    """Serialize a Settings attribute to a string for forms/storage."""
    if value is None:
        return ""
    if spec.type is SettingType.BOOL:
        return "true" if bool(value) else "false"
    if spec.type in {SettingType.CSV_LIST, SettingType.INT_LIST}:
        if isinstance(value, list):
            if spec.type is SettingType.INT_LIST:
                return ",".join(str(v) for v in value)
            return ",".join(str(v) for v in value)
        return str(value)
    if spec.type is SettingType.SPACE_LIST:
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        return str(value)
    if spec.type is SettingType.PATH:
        return str(value)
    return str(value)


def parse_form_value(raw: str | None, spec: SettingSpec) -> str:
    """Normalize a submitted form value to a storage string."""
    if spec.type is SettingType.BOOL:
        return "true" if raw in {"on", "true", "1", "yes"} else "false"
    return (raw or "").strip()


def coerce_storage_value(raw: str, spec: SettingSpec) -> object:
    """Convert a stored string to the Python type expected by Settings."""
    if spec.type is SettingType.BOOL:
        return raw.lower() in {"1", "true", "yes", "on"}
    if spec.type is SettingType.INT:
        return int(raw)
    if spec.type is SettingType.PATH:
        return Path(raw) if raw else None
    if spec.type is SettingType.ENUM:
        return raw
    if spec.type is SettingType.CSV_LIST:
        return [x.strip() for x in raw.split(",") if x.strip()]
    if spec.type is SettingType.SPACE_LIST:
        return [x for x in raw.split() if x]
    if spec.type is SettingType.INT_LIST:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    return raw
