"""Tests for cleanup_stale_output()."""
from __future__ import annotations

from pathlib import Path

from maker_file_index.cleanup import cleanup_stale_output
from maker_file_index.model import IndexRecord


def _make_record(path: Path) -> IndexRecord:
    return IndexRecord(
        path=path,
        directory=path.parent,
        notes="",
        thumbnail_path=Path(""),
        error="",
    )


def test_cleanup_removes_stale_html(tmp_path):
    root_dir = tmp_path / "source"
    out_dir = tmp_path / "output"
    dirs_root = out_dir / "dirs"

    # Create a real source file
    (root_dir / "subdir").mkdir(parents=True)
    real_file = root_dir / "subdir" / "real.lbrn2"
    real_file.write_text("<LightBurnProject/>")

    # Create expected output for real file
    (dirs_root / "subdir").mkdir(parents=True)
    (dirs_root / "subdir" / "index.html").write_text("index")
    (dirs_root / "subdir" / "real.html").write_text("detail")

    # Create a stale file with no corresponding source record
    (dirs_root / "subdir" / "stale.html").write_text("stale")

    records = [_make_record(real_file)]
    n = cleanup_stale_output(records, out_dir=out_dir, root_dir=root_dir)

    assert n == 1
    assert not (dirs_root / "subdir" / "stale.html").exists()
    assert (dirs_root / "subdir" / "real.html").exists()


def test_cleanup_keeps_expected_md(tmp_path):
    root_dir = tmp_path / "source"
    out_dir = tmp_path / "output"
    dirs_root = out_dir / "dirs"

    (root_dir / "sub").mkdir(parents=True)
    real_file = root_dir / "sub" / "part.stl"
    real_file.write_bytes(b"\x00" * 84)

    (dirs_root / "sub").mkdir(parents=True)
    (dirs_root / "sub" / "index.md").write_text("index")
    (dirs_root / "sub" / "part.md").write_text("detail")

    records = [_make_record(real_file)]
    n = cleanup_stale_output(records, out_dir=out_dir, root_dir=root_dir)

    assert n == 0
    assert (dirs_root / "sub" / "part.md").exists()
    assert (dirs_root / "sub" / "index.md").exists()


def test_cleanup_removes_thumbnail_not_in_records(tmp_path):
    root_dir = tmp_path / "source"
    out_dir = tmp_path / "output"
    dirs_root = out_dir / "dirs"

    (root_dir / "sub").mkdir(parents=True)
    real_file = root_dir / "sub" / "part.stl"
    real_file.write_bytes(b"\x00" * 84)

    (dirs_root / "sub").mkdir(parents=True)
    # A thumbnail that belongs to a file that no longer exists
    stale_thumb = dirs_root / "sub" / "deleted_thumbnail.png"
    stale_thumb.write_bytes(b"PNG")
    # Expected files
    (dirs_root / "sub" / "index.html").write_text("index")

    records = [_make_record(real_file)]
    n = cleanup_stale_output(records, out_dir=out_dir, root_dir=root_dir)

    assert n == 1
    assert not stale_thumb.exists()


def test_cleanup_does_nothing_when_dirs_absent(tmp_path):
    root_dir = tmp_path / "source"
    out_dir = tmp_path / "output"
    # out_dir/dirs does not exist
    out_dir.mkdir()

    real_file = root_dir / "part.stl"
    records = [_make_record(real_file)]
    n = cleanup_stale_output(records, out_dir=out_dir, root_dir=root_dir)
    assert n == 0


def test_cleanup_removes_empty_directories(tmp_path):
    root_dir = tmp_path / "source"
    out_dir = tmp_path / "output"
    dirs_root = out_dir / "dirs"

    (root_dir / "sub").mkdir(parents=True)
    real_file = root_dir / "sub" / "part.stl"
    real_file.write_bytes(b"\x00" * 84)

    # Create a directory with only stale files
    (dirs_root / "orphan").mkdir(parents=True)
    (dirs_root / "orphan" / "ghost.html").write_text("ghost")

    # Also create minimal expected files
    (dirs_root / "sub").mkdir(parents=True)
    (dirs_root / "sub" / "index.html").write_text("index")

    records = [_make_record(real_file)]
    n = cleanup_stale_output(records, out_dir=out_dir, root_dir=root_dir)

    assert n >= 1
    assert not (dirs_root / "orphan" / "ghost.html").exists()
    # Empty orphan dir should be removed too
    assert not (dirs_root / "orphan").exists()
