"""Tests for thumbnail_path_for() and thumbnail_is_fresh()."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from maker_file_index.thumbnails import thumbnail_is_fresh, thumbnail_path_for


# ---------------------------------------------------------------------------
# thumbnail_path_for
# ---------------------------------------------------------------------------

def test_sidecar_default(tmp_path):
    src = tmp_path / "model.stl"
    result = thumbnail_path_for(src)
    assert result == tmp_path / "model_thumbnail.png"


def test_sidecar_custom_suffix(tmp_path):
    src = tmp_path / "model.stl"
    result = thumbnail_path_for(src, suffix="_thumb.bmp")
    assert result == tmp_path / "model_thumb.bmp"


def test_with_thumb_root_and_scan_root(tmp_path):
    scan_root = tmp_path / "source"
    thumb_root = tmp_path / "output" / "dirs"
    src = scan_root / "subfolder" / "model.stl"

    result = thumbnail_path_for(src, thumb_root=thumb_root, scan_root=scan_root)
    assert result == thumb_root / "subfolder" / "model_thumbnail.png"


def test_with_thumb_root_nested_path(tmp_path):
    scan_root = tmp_path / "source"
    thumb_root = tmp_path / "output" / "dirs"
    src = scan_root / "a" / "b" / "c" / "model.stl"

    result = thumbnail_path_for(src, thumb_root=thumb_root, scan_root=scan_root)
    assert result == thumb_root / "a" / "b" / "c" / "model_thumbnail.png"


def test_source_outside_scan_root_falls_back(tmp_path):
    """If source is not under scan_root, falls back to parent name only."""
    scan_root = tmp_path / "source"
    thumb_root = tmp_path / "output" / "dirs"
    src = tmp_path / "elsewhere" / "model.stl"

    result = thumbnail_path_for(src, thumb_root=thumb_root, scan_root=scan_root)
    # Falls back to thumb_root / parent_name / stem_thumbnail.png
    assert result == thumb_root / "elsewhere" / "model_thumbnail.png"


def test_thumb_root_without_scan_root_uses_sidecar(tmp_path):
    """thumb_root alone (without scan_root) is ignored — falls back to sidecar."""
    src = tmp_path / "model.stl"
    thumb_root = tmp_path / "output"
    result = thumbnail_path_for(src, thumb_root=thumb_root)
    assert result == tmp_path / "model_thumbnail.png"


# ---------------------------------------------------------------------------
# thumbnail_is_fresh
# ---------------------------------------------------------------------------

def test_fresh_when_thumb_newer(tmp_path):
    src = tmp_path / "source.stl"
    thumb = tmp_path / "source_thumbnail.png"
    src.write_bytes(b"x")
    time.sleep(0.05)
    thumb.write_bytes(b"png")
    assert thumbnail_is_fresh(src, thumb) is True


def test_not_fresh_when_thumb_older(tmp_path):
    src = tmp_path / "source.stl"
    thumb = tmp_path / "source_thumbnail.png"
    thumb.write_bytes(b"png")
    time.sleep(0.05)
    src.write_bytes(b"x")
    assert thumbnail_is_fresh(src, thumb) is False


def test_not_fresh_when_thumb_missing(tmp_path):
    src = tmp_path / "source.stl"
    src.write_bytes(b"x")
    thumb = tmp_path / "source_thumbnail.png"
    assert thumbnail_is_fresh(src, thumb) is False


def test_not_fresh_when_source_missing(tmp_path):
    """OSError on missing source → not fresh."""
    src = tmp_path / "nonexistent.stl"
    thumb = tmp_path / "source_thumbnail.png"
    thumb.write_bytes(b"png")
    assert thumbnail_is_fresh(src, thumb) is False
