"""Application configuration.

Priority (highest to lowest):
  1. Environment variables
  2. /config/config.yaml (if present)
  3. Defaults defined here
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG_YAML_PATH = Path(os.getenv("CONFIG_FILE", "/config/config.yaml"))


def _load_yaml() -> dict[str, Any]:
    """Load YAML config file if it exists, returning a flat env-style dict."""
    if not _CONFIG_YAML_PATH.exists():
        return {}

    with _CONFIG_YAML_PATH.open() as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    flat: dict[str, Any] = {}

    # app section
    app = raw.get("app", {})
    flat.update(
        {
            "APP_HOST": app.get("host", None),
            "APP_PORT": app.get("port", None),
            "APP_BASE_URL": app.get("base_url", None),
            "APP_SECRET_KEY": app.get("secret_key", None),
            "AUTH_ENABLED": app.get("auth_enabled", None),
            "AUTH_USERNAME": app.get("auth_username", None),
            "AUTH_PASSWORD": app.get("auth_password", None),
        }
    )

    # paths section
    paths = raw.get("paths", {})
    flat.update(
        {
            "WORK_DIR": paths.get("work_dir", None),
            "ARCHIVE_FILE": paths.get("archive_file", None),
            "OUTPUT_ROOT": paths.get("output_root", None),
        }
    )

    # download section
    dl = raw.get("download", {})
    flat.update(
        {
            "ALLOW_PLAYLISTS": dl.get("allow_playlists", None),
            "ALLOW_CHANNELS": dl.get("allow_channels", None),
            "DEFAULT_DESTINATION_FOLDER": dl.get("default_destination_folder", None),
            "YTDLP_AUDIO_FORMAT": dl.get("audio_format", None),
            "YTDLP_AUDIO_QUALITY": dl.get("audio_quality", None),
            "YTDLP_EXTRA_ARGS": dl.get("yt_dlp_extra_args", None),
            "FFMPEG_EXTRA_ARGS": dl.get("ffmpeg_extra_args", None),
            "OUTPUT_EXTENSION": dl.get("output_extension", None),
            "FILENAME_TEMPLATE": dl.get("filename_template", None),
            "FOLDER_NAME_FIELD": dl.get("folder_name_field", None),
            "FOLDER_NAME_FALLBACKS": dl.get("folder_name_fallbacks", None),
            "COLLISION_MODE": dl.get("collision_mode", None),
        }
    )

    # jobs section
    jobs = raw.get("jobs", {})
    flat.update(
        {
            "MAX_CONCURRENT_JOBS": jobs.get("max_concurrent_jobs", None),
            "JOB_TIMEOUT_SECONDS": jobs.get("timeout_seconds", None),
            "RETRY_MAX": jobs.get("retry_max", None),
            "RETRY_INTERVAL_SECONDS": jobs.get("retry_intervals_seconds", None),
            "CLEANUP_TEMP_ON_SUCCESS": jobs.get("cleanup_temp_on_success", None),
            "CLEANUP_TEMP_ON_FAILURE": jobs.get("cleanup_temp_on_failure", None),
        }
    )

    # audiobookshelf section
    abs_cfg = raw.get("audiobookshelf", {})
    flat.update(
        {
            "ABS_BASE_URL": abs_cfg.get("base_url", None),
            "ABS_API_TOKEN": abs_cfg.get("api_token", None),
            "ABS_LIBRARY_ID": abs_cfg.get("library_id", None),
            "ABS_SCAN_AFTER_SUCCESS": abs_cfg.get("scan_after_success", None),
        }
    )

    # Remove None values so they don't override env vars
    return {k: v for k, v in flat.items() if v is not None}


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------

ALLOWED_DOMAINS_DEFAULT = [
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
]


def _get_default_data_dir() -> Path:
    """Return /data if writable/creatable, otherwise fallback to local ./data."""
    p = Path("/data")
    try:
        p.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = p / ".write_test"
        test_file.touch()
        test_file.unlink()
        return p
    except Exception:
        fallback = Path("./data")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Tell pydantic-settings to use comma as list delimiter for env vars
        env_nested_delimiter=None,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_host: str = Field("0.0.0.0", alias="APP_HOST")  # noqa: S104
    app_port: int = Field(8080, alias="APP_PORT")
    app_base_url: str | None = Field(None, alias="APP_BASE_URL")
    app_secret_key: str = Field("changeme-set-app-secret-key", alias="APP_SECRET_KEY")

    # ── Auth ─────────────────────────────────────────────────────────────────
    auth_enabled: bool = Field(False, alias="AUTH_ENABLED")
    auth_username: str | None = Field(None, alias="AUTH_USERNAME")
    auth_password: str | None = Field(None, alias="AUTH_PASSWORD")

    # ── Browser Extension API ──────────────────────────────────────────────
    extension_api_enabled: bool = Field(
        False,
        alias="EXTENSION_API_ENABLED",
        description="Enable extension API endpoints (returns 404 if false)",
    )
    extension_api_token: str | None = Field(
        None,
        alias="EXTENSION_API_TOKEN",
        description="Optional bearer token for extension API. "
        "If set, requires Authorization: Bearer <token> or X-ABS-MEDIA-IMPORTER-Token headers.",
    )

    # ── Infrastructure ───────────────────────────────────────────────────────
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")
    database_url: str = Field(
        default_factory=lambda: f"sqlite+aiosqlite:///{_get_default_data_dir()}/app.db",
        alias="DATABASE_URL",
    )

    # ── Paths ─────────────────────────────────────────────────────────────────
    work_dir: Path = Field(
        default_factory=lambda: _get_default_data_dir() / "work", alias="WORK_DIR"
    )
    archive_file: Path = Field(
        default_factory=lambda: _get_default_data_dir() / "config" / "youtube-archive.txt",
        alias="ARCHIVE_FILE",
    )
    output_root: Path = Field(Path("/media/podcasts"), alias="OUTPUT_ROOT")

    # ── Download ─────────────────────────────────────────────────────────────
    allow_playlists: bool = Field(False, alias="ALLOW_PLAYLISTS")
    allow_channels: bool = Field(False, alias="ALLOW_CHANNELS")
    default_destination_folder: str | None = Field(None, alias="DEFAULT_DESTINATION_FOLDER")

    ytdlp_bin: str = Field("yt-dlp", alias="YTDLP_BIN")
    ffmpeg_bin: str = Field("ffmpeg", alias="FFMPEG_BIN")
    ffprobe_bin: str = Field("ffprobe", alias="FFPROBE_BIN")
    ytdlp_audio_format: str = Field("m4a", alias="YTDLP_AUDIO_FORMAT")
    ytdlp_audio_quality: str = Field("", alias="YTDLP_AUDIO_QUALITY")
    ytdlp_extra_args: Any = Field(default_factory=lambda: [], alias="YTDLP_EXTRA_ARGS")
    ffmpeg_extra_args: Any = Field(default_factory=lambda: [], alias="FFMPEG_EXTRA_ARGS")

    output_extension: str = Field("m4b", alias="OUTPUT_EXTENSION")
    filename_template: str = Field("{title}.m4b", alias="FILENAME_TEMPLATE")
    folder_name_field: str = Field("uploader_id", alias="FOLDER_NAME_FIELD")
    folder_name_fallbacks: Any = Field(
        default_factory=lambda: ["uploader_id", "channel_id", "channel", "uploader"],
        alias="FOLDER_NAME_FALLBACKS",
    )
    collision_mode: str = Field("append_id", alias="COLLISION_MODE")

    allowed_domains: Any = Field(
        default_factory=lambda: list(ALLOWED_DOMAINS_DEFAULT),
        alias="ALLOWED_DOMAINS",
    )

    # ── Jobs ─────────────────────────────────────────────────────────────────
    max_concurrent_jobs: int = Field(1, alias="MAX_CONCURRENT_JOBS")
    job_timeout_seconds: int = Field(10800, alias="JOB_TIMEOUT_SECONDS")
    retry_max: int = Field(3, alias="RETRY_MAX")
    retry_interval_seconds: Any = Field(
        default_factory=lambda: [60, 300, 900],
        alias="RETRY_INTERVAL_SECONDS",
    )
    cleanup_temp_on_success: bool = Field(True, alias="CLEANUP_TEMP_ON_SUCCESS")
    cleanup_temp_on_failure: bool = Field(False, alias="CLEANUP_TEMP_ON_FAILURE")

    # ── Audiobookshelf ────────────────────────────────────────────────────────
    abs_base_url: str | None = Field(None, alias="ABS_BASE_URL")
    abs_api_token: str | None = Field(None, alias="ABS_API_TOKEN")
    abs_library_id: str | None = Field(None, alias="ABS_LIBRARY_ID")
    abs_scan_after_success: bool = Field(False, alias="ABS_SCAN_AFTER_SUCCESS")

    # ── Dev ───────────────────────────────────────────────────────────────────
    dry_run: bool = Field(False, alias="DRY_RUN")

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("ytdlp_extra_args", "ffmpeg_extra_args", mode="before")
    @classmethod
    def parse_space_separated_list(cls, v: Any) -> Any:  # noqa: ANN401
        if isinstance(v, str):
            return [x for x in v.split() if x]
        return v

    @field_validator("folder_name_fallbacks", mode="before")
    @classmethod
    def parse_comma_list(cls, v: Any) -> Any:  # noqa: ANN401
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("retry_interval_seconds", mode="before")
    @classmethod
    def parse_int_list(cls, v: Any) -> Any:  # noqa: ANN401
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def parse_domains(cls, v: Any) -> Any:  # noqa: ANN401
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("collision_mode")
    @classmethod
    def validate_collision_mode(cls, v: str) -> str:
        valid = {"skip", "overwrite", "append_id", "append_counter"}
        if v not in valid:
            raise ValueError(f"collision_mode must be one of {valid}")
        return v

    @field_validator("extension_api_token", mode="before")
    @classmethod
    def validate_extension_api_token(cls, v: str) -> str | None:
        if v is None or v == "":
            return None
        # Optionally validate length if you want
        return v

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def abs_configured(self) -> bool:
        return bool(self.abs_base_url and self.abs_api_token and self.abs_library_id)

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for use in RQ worker (not async)."""
        return self.database_url.replace("+aiosqlite", "")


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_settings: Settings | None = None


def _load_custom_settings(settings: Settings) -> None:
    """Load user custom settings from json file on disk if exists."""
    import json

    path = _get_default_data_dir() / "settings.json"
    if path.exists():
        try:
            with path.open() as fh:
                data = json.load(fh)
            if "output_root" in data:
                settings.output_root = Path(data["output_root"])
            if "dry_run" in data:
                settings.dry_run = bool(data["dry_run"])
            if "allow_playlists" in data:
                settings.allow_playlists = bool(data["allow_playlists"])
            if "allow_channels" in data:
                settings.allow_channels = bool(data["allow_channels"])
            if "abs_scan_after_success" in data:
                settings.abs_scan_after_success = bool(data["abs_scan_after_success"])
        except Exception:  # noqa: S110
            pass


def save_custom_settings(
    output_root: str,
    *,
    dry_run: bool | None = None,
    allow_playlists: bool | None = None,
    allow_channels: bool | None = None,
    abs_scan_after_success: bool | None = None,
) -> None:
    """Write custom settings to settings.json and clear settings cache."""
    import json

    path = _get_default_data_dir() / "settings.json"
    data = {}
    if path.exists():
        try:
            with path.open() as fh:
                data = json.load(fh)
        except Exception:  # noqa: S110
            pass

    data["output_root"] = output_root.strip()
    if dry_run is not None:
        data["dry_run"] = bool(dry_run)
    if allow_playlists is not None:
        data["allow_playlists"] = bool(allow_playlists)
    if allow_channels is not None:
        data["allow_channels"] = bool(allow_channels)
    if abs_scan_after_success is not None:
        data["abs_scan_after_success"] = bool(abs_scan_after_success)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(data, fh, indent=2)

    global _settings
    _settings = None


def reload_settings() -> Settings:
    """Force settings reload and return a fresh settings instance."""
    global _settings
    _settings = None
    return get_settings()


def get_settings() -> Settings:
    """Return cached settings instance, merging YAML values under env vars."""
    global _settings
    if _settings is None:
        yaml_values = _load_yaml()
        # Set missing env vars from YAML so pydantic picks them up
        for key, val in yaml_values.items():
            if key not in os.environ:
                if isinstance(val, list):
                    os.environ[key] = ",".join(str(x) for x in val)
                else:
                    os.environ[key] = str(val)
        _settings = Settings()
        _load_custom_settings(_settings)
    return _settings
