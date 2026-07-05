"""Tests for app.path_checks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from app.path_checks import check_readable_file, check_writable_directory, parse_absolute_file_path


def test_writable_directory_passes(tmp_path: Path):
    assert check_writable_directory(tmp_path, create=True) is None


def test_writable_directory_creates_missing_path(tmp_path: Path):
    target = tmp_path / "nested" / "output"
    assert check_writable_directory(target, create=True) is None
    assert target.is_dir()


def test_relative_path_fails(tmp_path: Path):
    os.chdir(tmp_path)
    error = check_writable_directory(Path("relative/path"), create=True)
    assert error == "Path must be absolute."


def test_nonexistent_without_create_fails(tmp_path: Path):
    missing = tmp_path / "missing"
    error = check_writable_directory(missing, create=False)
    assert error is not None
    assert "does not exist" in error


def test_read_only_directory_fails(tmp_path: Path):
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(stat.S_IRUSR | stat.S_IXUSR)

    try:
        error = check_writable_directory(read_only, create=False)
    finally:
        read_only.chmod(stat.S_IRWXU)

    assert error is not None
    assert "not writable" in error


def test_file_path_fails(tmp_path: Path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")

    error = check_writable_directory(file_path, create=False)
    assert error is not None
    assert "bind mount is not available yet" in error


def test_parse_absolute_file_path_rejects_relative_and_traversal(tmp_path: Path):
    assert parse_absolute_file_path(str(tmp_path / "cookies.txt")) is not None
    assert parse_absolute_file_path("relative/cookies.txt") is None
    assert parse_absolute_file_path(str(tmp_path / ".." / "escape.txt")) is None
    assert parse_absolute_file_path("cookies.txt\0") is None


def test_check_readable_file_warns_when_missing(tmp_path: Path):
    missing = tmp_path / "missing-cookies.txt"
    error, warning = check_readable_file(missing.resolve())
    assert error is None
    assert warning is not None
    assert "does not exist" in warning


def test_check_readable_file_passes_for_readable_file(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    error, warning = check_readable_file(cookies.resolve())
    assert error is None
    assert warning is None
