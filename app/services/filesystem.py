"""Filesystem service: folder listing, path safety, filename sanitization."""

from __future__ import annotations

import contextlib
import logging
import re
import shutil
import unicodedata
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

# Characters not allowed in filenames (cross-platform safe)
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r"\s{2,}")
_LEADING_TRAILING_DOTS = re.compile(r"^\.+|\.+$")


def safe_filename(name: str, max_length: int = 200) -> str:
    """
    Return a filesystem-safe version of *name*.

    - Normalizes Unicode to NFC
    - Strips control characters and characters unsafe on Windows/POSIX
    - Collapses multiple spaces
    - Strips leading/trailing dots and spaces
    - Truncates to *max_length* characters
    - Falls back to 'untitled' if empty after sanitization
    """
    # Normalize unicode
    name = unicodedata.normalize("NFC", name)
    # Remove unsafe characters
    name = _UNSAFE_CHARS.sub("", name)
    # Collapse whitespace
    name = _MULTI_SPACE.sub(" ", name)
    # Strip
    name = name.strip(" .")
    # Truncate
    name = name[:max_length]
    # Final strip
    name = name.strip(" .")
    return name or "untitled"


def safe_folder_name(name: str) -> str:
    """Slightly more permissive than safe_filename; used for folder creation."""
    return safe_filename(name, max_length=100)


def render_filename_template(
    template: str,
    *,
    title: str,
    video_id: str,
    uploader: str | None = None,
    channel: str | None = None,
    upload_date: str | None = None,
) -> str:
    """Render a filename template with supported placeholders."""
    fields = {
        "title": title,
        "video_id": video_id,
        "uploader": uploader or "",
        "channel": channel or "",
        "upload_date": upload_date or "",
    }
    rendered = template
    for key, value in fields.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return safe_filename(rendered)


def _strip_extension_suffix(stem: str, ext: str) -> str:
    """Remove a trailing .ext from *stem* when the template already included it."""
    suffix = f".{ext.lstrip('.')}"
    if stem.lower().endswith(suffix.lower()):
        return stem[: -len(suffix)]
    return stem


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def resolve_safe_path(root: Path, relative: str) -> Path:
    """
    Resolve *relative* inside *root*, raising ValueError on path traversal.

    *relative* must resolve to a path that is *root* or a child of *root*.
    """
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        is_safe = candidate.is_relative_to(root)
    except AttributeError:
        try:
            candidate.relative_to(root)
            is_safe = True
        except ValueError:
            is_safe = False

    if not is_safe:
        raise ValueError(f"Path traversal detected: '{relative}' resolves outside root '{root}'")
    return candidate


def assert_within_root(root: Path, path: Path) -> None:
    """Raise ValueError if *path* is not under *root*."""
    root = root.resolve()
    path = path.resolve()
    try:
        is_safe = path.is_relative_to(root)
    except AttributeError:
        try:
            path.relative_to(root)
            is_safe = True
        except ValueError:
            is_safe = False

    if not is_safe:
        raise ValueError(f"Path '{path}' is outside output root '{root}'")


# ---------------------------------------------------------------------------
# Folder listing
# ---------------------------------------------------------------------------


def list_folders(output_root: Path, recursive: bool = False) -> list[str]:
    """
    Return a sorted list of folder names (relative to *output_root*).

    By default lists only one level deep. If *recursive* is True, lists all
    nested directories. Returns relative POSIX paths.
    """
    try:
        if not output_root.exists():
            return []
    except OSError:
        return []

    results: list[str] = []
    try:
        if recursive:
            for item in sorted(output_root.rglob("*")):
                try:
                    if item.is_dir():
                        rel = item.relative_to(output_root)
                        results.append(rel.as_posix())
                except OSError:
                    continue
        else:
            for item in sorted(output_root.iterdir()):
                try:
                    if item.is_dir():
                        results.append(item.name)
                except OSError:
                    continue
    except OSError:
        return []

    return results


def create_destination_folder(output_root: Path, folder_name: str) -> Path:
    """
    Create a new destination folder inside *output_root*.

    Sanitizes *folder_name* and validates path traversal.
    Returns the created Path.
    """
    # Check traversal on unsanitized name first
    resolve_safe_path(output_root, folder_name)

    clean_name = safe_folder_name(folder_name)
    if not clean_name:
        raise ValueError("Folder name is empty after sanitization")

    new_path = resolve_safe_path(output_root, clean_name)
    new_path.mkdir(parents=True, exist_ok=True)
    return new_path


# ---------------------------------------------------------------------------
# Output path resolution with collision handling
# ---------------------------------------------------------------------------


def resolve_output_path(
    output_root: Path,
    destination_folder: str,
    title: str,
    video_id: str,
    collision_mode: str = "append_id",
    extension: str = "m4b",
    filename_template: str = "{title}.m4b",
    uploader: str | None = None,
    channel: str | None = None,
    upload_date: str | None = None,
) -> Path:
    """
    Determine the final output .m4b path, applying collision handling.

    Collision modes:
      - skip:           Return existing path (caller should skip if exists).
      - overwrite:      Return existing path (caller overwrites).
      - append_id:      Append [video_id] before extension.
      - append_counter: Append (1), (2), ... until unique.

    Returns an absolute Path that is guaranteed to be inside *output_root*.
    Raises ValueError on path traversal.
    """
    ext = extension.lstrip(".")
    rendered = render_filename_template(
        filename_template,
        title=title,
        video_id=video_id,
        uploader=uploader,
        channel=channel,
        upload_date=upload_date,
    )
    safe_name = _strip_extension_suffix(rendered, ext)
    folder_path = resolve_safe_path(output_root, destination_folder)
    assert_within_root(output_root, folder_path)

    base_path = folder_path / f"{safe_name}.{ext}"

    if not base_path.exists():
        return base_path

    # Collision handling
    if collision_mode in {"skip", "overwrite"}:
        return base_path

    if collision_mode == "append_id":
        candidate = folder_path / f"{safe_name} [{video_id}].{ext}"
        return candidate

    if collision_mode == "append_counter":
        counter = 1
        while True:
            candidate = folder_path / f"{safe_name} ({counter}).{ext}"
            if not candidate.exists():
                return candidate
            counter += 1
            if counter > 9999:
                raise RuntimeError("Too many output file collisions")

    return base_path


# ---------------------------------------------------------------------------
# Staged output (write to work dir, commit atomically to final path)
# ---------------------------------------------------------------------------


def staged_output_path(work_dir: Path, final_path: Path) -> Path:
    """
    Return a per-job staged output path inside *work_dir*.

    The staged file lives at ``<work_dir>/staged/<final_filename>.partial`` so
    that Audiobookshelf (or any other scanner watching *final_path.parent*)
    never sees a partially written .m4b during conversion.
    """
    return work_dir / "staged" / f"{final_path.name}.partial"


def commit_staged_output(staged_path: Path, final_path: Path) -> None:
    """
    Publish *staged_path* as *final_path* using a sibling ``.partial`` temp file.

    Steps:
      1. Ensure the final output directory exists.
      2. Copy the staged file to ``<final_path>.partial`` via ``shutil.copy2``.
      3. Sanity-check the copied size against the staged size.
      4. Atomically replace the temp sibling onto *final_path*.

    On any failure the sibling temp is removed and the exception is re-raised.
    The staged file is left in place for the caller to inspect / clean up.
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_final = final_path.with_name(final_path.name + ".partial")

    if not staged_path.exists():
        raise FileNotFoundError(f"Staged output not found: {staged_path}")
    staged_size = staged_path.stat().st_size

    try:
        # copy2 is used because staged_path (work dir) and final_path (output
        # root) may live on different filesystems, in which case Path.replace
        # would fail with EXDEV. Copying to a sibling of final_path guarantees
        # the subsequent replace() is same-filesystem and therefore atomic.
        shutil.copy2(staged_path, temp_final)
        temp_size = temp_final.stat().st_size
        if temp_size != staged_size:
            raise RuntimeError(f"Size mismatch after copy: staged={staged_size} temp={temp_size}")
        temp_final.replace(final_path)
    except Exception:
        with contextlib.suppress(OSError):
            if temp_final.exists():
                temp_final.unlink()
        raise


def cleanup_output_partials(*paths: Path | None) -> None:
    """Best-effort removal of staged/partial artifacts. Never raises."""
    for path in paths:
        if path is None:
            continue
        with contextlib.suppress(OSError):
            if path.exists() and path.is_file():
                path.unlink()


# ---------------------------------------------------------------------------
# Filesystem service class (wraps helpers with Settings)
# ---------------------------------------------------------------------------


class FilesystemService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_folders(self, recursive: bool = False) -> list[str]:
        return list_folders(self.settings.output_root, recursive=recursive)

    def create_folder(self, folder_name: str) -> Path:
        return create_destination_folder(self.settings.output_root, folder_name)

    def resolve_output_path(
        self,
        destination_folder: str,
        title: str,
        video_id: str,
        collision_mode: str | None = None,
        extension: str | None = None,
        filename_template: str | None = None,
        uploader: str | None = None,
        channel: str | None = None,
        upload_date: str | None = None,
    ) -> Path:
        mode = collision_mode or self.settings.collision_mode
        return resolve_output_path(
            self.settings.output_root,
            destination_folder,
            title,
            video_id,
            mode,
            extension or self.settings.output_extension,
            filename_template or self.settings.filename_template,
            uploader=uploader,
            channel=channel,
            upload_date=upload_date,
        )

    def ensure_work_dir(self, job_id: str) -> Path:
        """Create and return the work directory for *job_id*."""
        work = self.settings.work_dir / job_id
        work.mkdir(parents=True, exist_ok=True)
        return work

    def log_path(self, job_id: str) -> Path:
        """Return the log file path for *job_id*."""
        log_dir = self.settings.work_dir.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{job_id}.log"

    def cleanup_work_dir(self, job_id: str) -> None:
        """Remove the job's temporary work directory."""
        work = self.settings.work_dir / job_id
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)

    def staged_output_path(self, job_id: str, final_path: Path) -> Path:
        """Return the staged output path for *job_id* / *final_path*."""
        return staged_output_path(self.settings.work_dir / job_id, final_path)

    def commit_staged_output(self, staged_path: Path, final_path: Path) -> None:
        """Commit *staged_path* to *final_path* via a sibling temp file."""
        commit_staged_output(staged_path, final_path)

    def cleanup_output_partials(self, *paths: Path | None) -> None:
        """Best-effort removal of staged/partial artifacts."""
        cleanup_output_partials(*paths)
