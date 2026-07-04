"""yt-dlp service: URL validation, preview, and download command building."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class VideoMetadata:
    """Subset of yt-dlp --dump-json output used by the app."""

    id: str
    title: str
    uploader: str | None = None
    uploader_id: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    duration: int | None = None  # seconds
    upload_date: str | None = None  # YYYYMMDD
    thumbnail: str | None = None
    chapters: list[dict[str, Any]] = field(default_factory=list)
    webpage_url: str = ""

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> VideoMetadata:
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            uploader=data.get("uploader"),
            uploader_id=data.get("uploader_id"),
            channel=data.get("channel"),
            channel_id=data.get("channel_id"),
            duration=data.get("duration"),
            upload_date=data.get("upload_date"),
            thumbnail=data.get("thumbnail"),
            chapters=data.get("chapters") or [],
            webpage_url=data.get("webpage_url", ""),
        )


@dataclass
class PlaylistEntry:
    """One video entry from a flat-playlist enumeration."""

    id: str
    title: str
    url: str
    duration: int | None = None
    uploader: str | None = None
    uploader_id: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    thumbnail: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PlaylistEntry | None:
        video_id = (data.get("id") or "").strip()
        if not video_id:
            return None
        url = (data.get("url") or data.get("webpage_url") or "").strip()
        if not url:
            url = f"https://www.youtube.com/watch?v={video_id}"
        elif not url.startswith("http"):
            # Flat playlist entries sometimes return only the video id as url.
            url = f"https://www.youtube.com/watch?v={video_id}"
        duration = data.get("duration")
        if duration is not None:
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                duration = None
        thumbnail = data.get("thumbnail")
        if not thumbnail:
            thumbnails = data.get("thumbnails") or []
            if thumbnails and isinstance(thumbnails[-1], dict):
                thumbnail = thumbnails[-1].get("url")
        return cls(
            id=video_id,
            title=(data.get("title") or video_id).strip() or video_id,
            url=url,
            duration=duration,
            uploader=data.get("uploader"),
            uploader_id=data.get("uploader_id"),
            channel=data.get("channel"),
            channel_id=data.get("channel_id"),
            thumbnail=thumbnail,
        )


@dataclass
class PlaylistMetadata:
    """Flat-playlist / channel listing returned by yt-dlp."""

    id: str
    title: str
    source_type: str  # "playlist" | "channel"
    webpage_url: str = ""
    uploader: str | None = None
    uploader_id: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    thumbnail: str | None = None
    entries: list[PlaylistEntry] = field(default_factory=list)
    truncated: bool = False

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @classmethod
    def from_json(
        cls,
        data: dict[str, Any],
        *,
        source_type: str,
        limit: int,
    ) -> PlaylistMetadata:
        raw_entries = data.get("entries") or []
        truncated = len(raw_entries) > limit
        entries: list[PlaylistEntry] = []
        for item in raw_entries[:limit]:
            if not isinstance(item, dict):
                continue
            entry = PlaylistEntry.from_json(item)
            if entry is not None:
                entries.append(entry)
        thumbnails = data.get("thumbnails") or []
        thumbnail = data.get("thumbnail")
        if not thumbnail and thumbnails and isinstance(thumbnails[-1], dict):
            thumbnail = thumbnails[-1].get("url")
        return cls(
            id=data.get("id") or "",
            title=data.get("title") or data.get("channel") or "Untitled",
            source_type=source_type,
            webpage_url=data.get("webpage_url") or data.get("original_url") or "",
            uploader=data.get("uploader"),
            uploader_id=data.get("uploader_id"),
            channel=data.get("channel"),
            channel_id=data.get("channel_id"),
            thumbnail=thumbnail,
            entries=entries,
            truncated=truncated,
        )


@dataclass
class UrlValidationResult:
    valid: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class YtDlpService:
    """Thin wrapper around yt-dlp subprocess calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_url(self, url: str) -> UrlValidationResult:
        """
        Validate that *url* is an acceptable YouTube URL.

        Returns UrlValidationResult with valid=True/False and optional error.
        """
        url = url.strip()
        if not url:
            return UrlValidationResult(False, "URL is empty")

        try:
            parsed = urlparse(url)
        except Exception:
            return UrlValidationResult(False, "Malformed URL")

        if parsed.scheme not in {"http", "https"}:
            return UrlValidationResult(False, "URL must use http or https")

        host = parsed.netloc.lower().removeprefix("www.")
        # Normalise: strip port if present
        host = host.split(":")[0]

        allowed = {d.lower().removeprefix("www.") for d in self.settings.allowed_domains}
        if host not in allowed and f"www.{host}" not in allowed:
            return UrlValidationResult(False, f"Domain '{host}' is not in the allowlist")

        # Detect playlist / channel patterns
        if not self.settings.allow_playlists and is_playlist_url(url):
            return UrlValidationResult(
                False,
                "Playlist URLs are not allowed (ALLOW_PLAYLISTS=false). Paste a single video URL.",
            )

        if not self.settings.allow_channels and is_channel_url(url):
            return UrlValidationResult(
                False,
                "Channel URLs are not allowed (ALLOW_CHANNELS=false). Paste a single video URL.",
            )

        return UrlValidationResult(True)

    # ── Preview ───────────────────────────────────────────────────────────────

    def _sanitize_command_url(self, url: str) -> str:
        """Normalize a URL before placing it on a subprocess argv list.

        Enforces structural safety only (scheme, allowlisted host, no control
        characters). Playlist/channel policy checks belong at the request
        boundary via ``validate_url``, not here — playlist command builders
        intentionally accept those URL shapes after policy has already passed.
        """
        safe_url = (url or "").strip()
        if not safe_url:
            raise ValueError("URL is required")
        if any(ch in safe_url for ch in ("\n", "\r", "\x00")):
            raise ValueError("URL contains invalid control characters")

        try:
            parsed = urlparse(safe_url)
        except Exception as exc:
            raise ValueError("Malformed URL") from exc

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only absolute http(s) URLs are allowed")

        host = parsed.netloc.lower().removeprefix("www.")
        host = host.split(":")[0]
        allowed = {d.lower().removeprefix("www.") for d in self.settings.allowed_domains}
        if host not in allowed and f"www.{host}" not in allowed:
            raise ValueError(f"Domain '{host}' is not in the allowlist")

        return safe_url

    def build_preview_command(self, url: str) -> list[str]:
        """Return the argument list for a metadata-only fetch."""
        safe_url = self._sanitize_command_url(url)
        return [
            self.settings.ytdlp_bin,
            "--skip-download",
            "--dump-json",
            "--no-playlist",
            "--",
            safe_url,
        ]

    def run_preview(self, url: str) -> VideoMetadata:
        """
        Run yt-dlp in metadata-only mode and return a VideoMetadata.

        Raises subprocess.CalledProcessError on failure.
        Raises ValueError if JSON cannot be parsed.
        """
        # Pass a list literal so the executable is a fixed first element; the
        # user-controlled URL is only an argument (shell=False).
        safe_url = self._sanitize_command_url(url)
        ytdlp = self.settings.ytdlp_bin
        logger.debug("Preview command: %s %s", ytdlp, safe_url)

        result = subprocess.run(
            [
                ytdlp,
                "--skip-download",
                "--dump-json",
                "--no-playlist",
                "--",
                safe_url,
            ],
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"yt-dlp returned invalid JSON: {exc}") from exc

        return VideoMetadata.from_json(data)

    # ── Playlist / channel enumeration ────────────────────────────────────────

    def build_flat_playlist_command(self, url: str, limit: int) -> list[str]:
        """Return the argument list for a capped flat-playlist listing.

        Fetches ``limit + 1`` entries so callers can detect truncation without
        paging the entire playlist or channel.
        """
        safe_url = self._sanitize_command_url(url)
        playlist_end = max(limit, 0) + 1
        return [
            self.settings.ytdlp_bin,
            "--skip-download",
            "--flat-playlist",
            "--dump-single-json",
            "--playlist-end",
            str(playlist_end),
            "--",
            safe_url,
        ]

    def run_playlist_preview(self, url: str, limit: int) -> PlaylistMetadata:
        """
        Enumerate videos in a playlist or channel URL (flat, metadata only).

        Raises subprocess.CalledProcessError on failure.
        Raises ValueError if JSON cannot be parsed or no entries are found.
        """
        if limit <= 0:
            raise ValueError("Playlist entry limit must be greater than zero")

        source_type = "channel" if is_channel_url(url) else "playlist"
        # Pass a list literal so the executable is a fixed first element; the
        # user-controlled URL is only an argument (shell=False). Building a
        # pre-tainted ``cmd`` list makes CodeQL treat the whole argv as
        # attacker-controlled (py/command-line-injection).
        safe_url = self._sanitize_command_url(url)
        playlist_end = str(max(limit, 0) + 1)
        ytdlp = self.settings.ytdlp_bin
        logger.debug("Playlist preview command: %s %s", ytdlp, safe_url)

        result = subprocess.run(
            [
                ytdlp,
                "--skip-download",
                "--flat-playlist",
                "--dump-single-json",
                "--playlist-end",
                playlist_end,
                "--",
                safe_url,
            ],
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"yt-dlp returned invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("yt-dlp returned unexpected playlist payload")

        meta = PlaylistMetadata.from_json(data, source_type=source_type, limit=limit)
        if not meta.entries:
            raise ValueError("No videos found in playlist or channel")
        if not meta.webpage_url:
            meta.webpage_url = safe_url
        return meta

    # ── Download ──────────────────────────────────────────────────────────────

    def build_download_command(
        self,
        url: str,
        job_id: str,
        output_template: str,
        *,
        embed_metadata: bool = True,
        embed_thumbnail: bool = True,
        embed_chapters: bool = True,
        use_archive: bool = True,
        force_archive_bypass: bool = False,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """
        Build the yt-dlp download command list.

        Args:
            url: YouTube URL.
            job_id: Used for logging context (not in command).
            output_template: yt-dlp -o template (absolute path).
            embed_metadata: Pass --embed-metadata.
            embed_thumbnail: Pass --embed-thumbnail.
            embed_chapters: Pass --embed-chapters.
            use_archive: Pass --download-archive flag.
            force_archive_bypass: If True, skip the archive flag even if configured.
            extra_args: Additional yt-dlp arguments to append.
        """
        s = self.settings
        cmd: list[str] = [
            s.ytdlp_bin,
            "--no-playlist",
            "-x",
            "--audio-format",
            s.ytdlp_audio_format,
            "--newline",
            "--progress",
        ]

        if s.ytdlp_audio_quality:
            cmd += ["--audio-quality", s.ytdlp_audio_quality]

        if embed_metadata:
            cmd.append("--embed-metadata")

        if embed_thumbnail:
            cmd.append("--embed-thumbnail")

        if embed_chapters:
            cmd.append("--embed-chapters")

        archive = s.archive_file
        if use_archive and not force_archive_bypass and archive:
            cmd += ["--download-archive", str(archive)]

        # Extra args from config
        if s.cookies_file:
            cmd += ["--cookies", str(s.cookies_file)]
        cmd.extend(s.ytdlp_extra_args)

        # Extra args from caller
        if extra_args:
            cmd.extend(extra_args)

        safe_url = self._sanitize_command_url(url)
        cmd += ["-o", output_template, "--", safe_url]

        return cmd

    def get_output_template(self, job_id: str) -> str:
        """Return the yt-dlp output template for a job."""
        s = self.settings
        template = "%(uploader_id,channel_id,channel,uploader|Unknown Channel)s/%(title)s.%(ext)s"
        return str(s.work_dir / job_id / "download" / template)

    def find_downloaded_file(self, job_id: str) -> Path | None:
        """
        Locate the downloaded audio file under the job's work dir.

        Returns the first .m4a (or configured format) file found, or None.
        """
        s = self.settings
        download_dir = s.work_dir / job_id / "download"
        if not download_dir.exists():
            return None

        ext = s.ytdlp_audio_format.lstrip(".")
        matches = list(download_dir.rglob(f"*.{ext}"))
        if matches:
            return matches[0]

        # Fallback: any audio file
        for pattern in ("*.m4a", "*.mp4", "*.opus", "*.webm"):
            found = list(download_dir.rglob(pattern))
            if found:
                return found[0]

        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_PLAYLIST_PATTERNS = [
    re.compile(r"[?&]list=", re.IGNORECASE),
    re.compile(r"/playlist", re.IGNORECASE),
]

_CHANNEL_PATTERNS = [
    re.compile(r"youtube\.com/channel/", re.IGNORECASE),
    re.compile(r"youtube\.com/c/", re.IGNORECASE),
    re.compile(r"youtube\.com/@[^/?]+/?$", re.IGNORECASE),
    re.compile(r"youtube\.com/user/", re.IGNORECASE),
    re.compile(r"youtube\.com/feeds/", re.IGNORECASE),
]


def is_playlist_url(url: str) -> bool:
    return any(p.search(url) for p in _PLAYLIST_PATTERNS)


def is_channel_url(url: str) -> bool:
    return any(p.search(url) for p in _CHANNEL_PATTERNS)


# ---------------------------------------------------------------------------
# Progress Parsing
# ---------------------------------------------------------------------------


@dataclass
class DownloadProgress:
    percent: float | None = None
    speed: str | None = None
    eta: str | None = None
    downloaded: str | None = None
    total: str | None = None
    raw_line: str | None = None


def parse_ytdlp_progress_line(line: str) -> DownloadProgress | None:
    """
    Parse a yt-dlp progress line and extract percentage, speed, ETA, and size.

    Returns None if the line is not a progress line.
    """
    line_str = line.strip()
    if not line_str.startswith("[download]"):
        return None

    # Check if there is a percentage
    pct_match = re.search(r"(\d+(?:\.\d+)?)%", line_str)
    if not pct_match:
        return None

    percent = float(pct_match.group(1))

    # Extract total size: "of <total>"
    total = None
    total_match = re.search(r"of\s+(~?\d+(?:\.\d+)?[a-zA-Z]+)", line_str)
    if total_match:
        total = total_match.group(1)

    # Extract speed: "at <speed>"
    speed = None
    speed_match = re.search(r"at\s+(\d+(?:\.\d+)?[a-zA-Z]+/s)", line_str)
    if speed_match:
        speed = speed_match.group(1)

    # Extract ETA: "ETA <eta>" or "in <eta>"
    eta = None
    eta_match = re.search(r"ETA\s+(\d+:\d+(?::\d+)?)", line_str)
    if eta_match:
        eta = eta_match.group(1)
    else:
        in_match = re.search(r"in\s+(\d+:\d+(?::\d+)?)", line_str)
        if in_match:
            eta = in_match.group(1)

    return DownloadProgress(
        percent=percent,
        speed=speed,
        eta=eta,
        total=total,
        raw_line=line_str,
    )
