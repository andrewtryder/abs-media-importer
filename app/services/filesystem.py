"""Filesystem service: folder listing, path safety, filename sanitization."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.config import Settings

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
    safe_name = safe_filename(title)
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
    ) -> Path:
        mode = collision_mode or self.settings.collision_mode
        return resolve_output_path(
            self.settings.output_root,
            destination_folder,
            title,
            video_id,
            mode,
            self.settings.output_extension,
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
        import shutil

        work = self.settings.work_dir / job_id
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
