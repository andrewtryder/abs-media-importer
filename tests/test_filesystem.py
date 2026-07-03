"""Tests for filesystem service."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.filesystem import (
    FilesystemService,
    assert_within_root,
    cleanup_output_partials,
    commit_staged_output,
    create_destination_folder,
    list_folders,
    resolve_output_path,
    resolve_safe_path,
    safe_filename,
    staged_output_path,
)

# ── safe_filename ──────────────────────────────────────────────────────────────


def test_safe_filename_basic():
    assert safe_filename("Hello World") == "Hello World"


def test_safe_filename_strips_unsafe_chars():
    result = safe_filename('My: Video "Title" <best>')
    assert ":" not in result
    assert '"' not in result
    assert "<" not in result
    assert ">" not in result


def test_safe_filename_unicode_preserved():
    result = safe_filename("Émile Zola — L'Assommoir")
    assert "Émile" in result
    assert "Zola" in result


def test_safe_filename_max_length():
    long_name = "A" * 300
    result = safe_filename(long_name)
    assert len(result) <= 200


def test_safe_filename_empty_fallback():
    result = safe_filename("   ...")
    assert result == "untitled"


def test_safe_filename_no_path_separators():
    result = safe_filename("../../etc/passwd")
    assert "/" not in result
    assert ".." not in result or result == "untitled"


# ── resolve_safe_path ──────────────────────────────────────────────────────────


def test_resolve_safe_path_ok(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    result = resolve_safe_path(root, "subdir")
    assert result.is_relative_to(root)


def test_resolve_safe_path_traversal(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="traversal"):
        resolve_safe_path(root, "../other")


def test_resolve_safe_path_double_dot(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="traversal"):
        resolve_safe_path(root, "a/../../etc")


def test_resolve_safe_path_sibling_prefix_escape(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    # Test sibling directory whose name starts with root's name
    sibling = tmp_path / "outside"
    sibling.mkdir()
    with pytest.raises(ValueError, match=r"outside root|traversal"):
        resolve_safe_path(root, "../outside")
    with pytest.raises(ValueError, match=r"outside root|traversal"):
        resolve_safe_path(root, "../out2")


def test_assert_within_root_ok(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    child = root / "subdir"
    child.mkdir()
    # Should not raise ValueError
    assert_within_root(root, child)
    assert_within_root(root, root)


def test_assert_within_root_sibling_prefix_escape(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    sibling = tmp_path / "outside"
    sibling.mkdir()
    with pytest.raises(ValueError, match=r"outside output root|outside"):
        assert_within_root(root, sibling)
    with pytest.raises(ValueError, match=r"outside output root|outside"):
        assert_within_root(root, tmp_path / "out2")


# ── list_folders ──────────────────────────────────────────────────────────────


def test_list_folders_empty(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir()
    assert list_folders(root) == []


def test_list_folders_single_level(tmp_path: Path):
    root = tmp_path / "podcasts"
    root.mkdir()
    (root / "ChannelA").mkdir()
    (root / "ChannelB").mkdir()
    (root / "file.txt").write_text("ignore")
    result = list_folders(root)
    assert "ChannelA" in result
    assert "ChannelB" in result
    assert "file.txt" not in result


def test_list_folders_nonexistent_root(tmp_path: Path):
    result = list_folders(tmp_path / "nope")
    assert result == []


def test_list_folders_handles_os_error(tmp_path: Path, mocker):
    root = tmp_path / "podcasts"
    root.mkdir()
    (root / "ChannelA").mkdir()
    (root / "ChannelB").mkdir()

    import os

    original_stat = os.stat

    def dummy_stat(path, *args, **kwargs):
        if "ChannelA" in str(path):
            raise OSError("Operation not supported")
        return original_stat(path, *args, **kwargs)

    mocker.patch("os.stat", side_effect=dummy_stat)

    # ChannelA should be gracefully skipped due to OSError, and ChannelB should be listed
    result = list_folders(root)
    assert "ChannelB" in result
    assert "ChannelA" not in result


def test_list_folders_recursive(tmp_path: Path):
    root = tmp_path / "podcasts"
    (root / "A" / "sub").mkdir(parents=True)
    (root / "B").mkdir(parents=True)
    result = list_folders(root, recursive=True)
    assert "A" in result
    assert "B" in result
    assert "A/sub" in result


# ── create_destination_folder ─────────────────────────────────────────────────


def test_create_folder_creates_dir(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    created = create_destination_folder(root, "@pintswithaquinas")
    assert created.exists()
    assert created.is_dir()


def test_create_folder_sanitizes_name(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    created = create_destination_folder(root, "My: Channel<Name>")
    assert created.exists()
    assert ":" not in created.name


def test_create_folder_traversal_rejected(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(ValueError):
        create_destination_folder(root, "../../etc")


# ── resolve_output_path ────────────────────────────────────────────────────────


def test_output_path_no_collision(tmp_path: Path):
    root = tmp_path / "out"
    folder = root / "ChannelA"
    folder.mkdir(parents=True)
    result = resolve_output_path(root, "ChannelA", "My Episode", "abc123")
    assert result.name == "My Episode.m4b"
    assert result.parent == folder


def test_output_path_collision_append_id(tmp_path: Path):
    root = tmp_path / "out"
    folder = root / "ChannelA"
    folder.mkdir(parents=True)
    existing = folder / "My Episode.m4b"
    existing.write_bytes(b"x")
    result = resolve_output_path(
        root, "ChannelA", "My Episode", "abc123", collision_mode="append_id"
    )
    assert "abc123" in result.name
    assert result.name == "My Episode [abc123].m4b"


def test_output_path_collision_skip(tmp_path: Path):
    root = tmp_path / "out"
    folder = root / "ChannelA"
    folder.mkdir(parents=True)
    existing = folder / "My Episode.m4b"
    existing.write_bytes(b"x")
    result = resolve_output_path(root, "ChannelA", "My Episode", "abc123", collision_mode="skip")
    assert result == existing


def test_output_path_collision_append_counter(tmp_path: Path):
    root = tmp_path / "out"
    folder = root / "ChannelA"
    folder.mkdir(parents=True)
    (folder / "My Episode.m4b").write_bytes(b"x")
    (folder / "My Episode (1).m4b").write_bytes(b"x")
    result = resolve_output_path(
        root, "ChannelA", "My Episode", "abc123", collision_mode="append_counter"
    )
    assert result.name == "My Episode (2).m4b"


def test_output_path_traversal_rejected(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_output_path(root, "../../etc", "title", "vid123")


# ── FilesystemService ─────────────────────────────────────────────────────────


def test_filesystem_service_list(default_settings, tmp_output_root: Path):
    (tmp_output_root / "ShowA").mkdir()
    (tmp_output_root / "ShowB").mkdir()
    svc = FilesystemService(default_settings)
    folders = svc.list_folders()
    assert "ShowA" in folders
    assert "ShowB" in folders


def test_filesystem_service_log_path(default_settings, tmp_work_dir: Path):
    svc = FilesystemService(default_settings)
    log = svc.log_path("test-job-id")
    assert log.name == "test-job-id.log"


def test_filesystem_service_cleanup(default_settings, tmp_work_dir: Path):
    svc = FilesystemService(default_settings)
    job_dir = tmp_work_dir / "job-abc"
    job_dir.mkdir()
    (job_dir / "file.m4a").write_bytes(b"audio")
    svc.cleanup_work_dir("job-abc")
    assert not job_dir.exists()


# ── Staged output helpers ─────────────────────────────────────────────────────


def test_staged_output_path_layout(tmp_path: Path):
    work_dir = tmp_path / "work" / "job-1"
    final_path = tmp_path / "podcasts" / "Show" / "Episode.m4b"
    staged = staged_output_path(work_dir, final_path)
    assert staged == work_dir / "staged" / "Episode.m4b.partial"


def test_commit_staged_output_happy_path(tmp_path: Path):
    staged = tmp_path / "work" / "staged" / "Ep.m4b.partial"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"hello world")

    final_path = tmp_path / "out" / "Show" / "Ep.m4b"
    commit_staged_output(staged, final_path)

    assert final_path.exists()
    assert final_path.read_bytes() == b"hello world"
    # Staging is not consumed by commit; caller cleans it up separately.
    assert staged.exists()
    # The temp sibling used during copy is renamed away.
    assert not final_path.with_name(final_path.name + ".partial").exists()


def test_commit_staged_output_missing_staged(tmp_path: Path):
    staged = tmp_path / "work" / "staged" / "Ep.m4b.partial"
    final_path = tmp_path / "out" / "Show" / "Ep.m4b"
    with pytest.raises(FileNotFoundError):
        commit_staged_output(staged, final_path)
    assert not final_path.exists()


def test_commit_staged_output_cleans_temp_on_failure(tmp_path: Path, monkeypatch):
    staged = tmp_path / "work" / "staged" / "Ep.m4b.partial"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"data")

    final_path = tmp_path / "out" / "Show" / "Ep.m4b"

    def broken_replace(_self, _target):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", broken_replace)

    with pytest.raises(OSError):
        commit_staged_output(staged, final_path)

    # Neither the final file nor the temp sibling should exist after failure.
    assert not final_path.exists()
    assert not final_path.with_name(final_path.name + ".partial").exists()


def test_cleanup_output_partials_removes_files(tmp_path: Path):
    a = tmp_path / "a.partial"
    b = tmp_path / "b.partial"
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    cleanup_output_partials(a, b, None, tmp_path / "does-not-exist.partial")
    assert not a.exists()
    assert not b.exists()


def test_filesystem_service_staged_helpers(default_settings, tmp_work_dir: Path):
    svc = FilesystemService(default_settings)
    final_path = default_settings.output_root / "Show" / "Ep.m4b"
    staged = svc.staged_output_path("job-x", final_path)
    assert staged == tmp_work_dir / "job-x" / "staged" / "Ep.m4b.partial"

    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"hi")
    svc.commit_staged_output(staged, final_path)
    assert final_path.exists()

    svc.cleanup_output_partials(staged)
    assert not staged.exists()
