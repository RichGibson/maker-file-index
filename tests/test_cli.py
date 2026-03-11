"""CLI smoke tests — run maker-file-index against the sample files/ directory."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FILES_DIR = REPO_ROOT / "files"


def run_cli(*args, **kwargs):
    return subprocess.run(
        [sys.executable, "-m", "maker_file_index.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        **kwargs,
    )


def test_help_exits_zero():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "maker-file-index" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_version_exits_zero():
    result = run_cli("--version")
    assert result.returncode == 0
    assert "maker-file-index" in result.stdout


def test_smoke_runs_against_files_dir(tmp_path):
    """Full run against sample files — assert exit 0 and key output files exist."""
    result = run_cli(str(FILES_DIR), "--output-dir", str(tmp_path))
    assert result.returncode == 0, (
        f"CLI failed with returncode {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    # Landing page and notes file must exist
    assert (tmp_path / "index.html").exists(), "index.html not generated"
    assert (tmp_path / "maker_file_notes.md").exists(), "maker_file_notes.md not generated"

    # dirs/ must exist and contain at least one HTML detail page
    dirs_root = tmp_path / "dirs"
    assert dirs_root.exists(), "dirs/ directory not created"
    html_files = list(dirs_root.rglob("*.html"))
    assert len(html_files) > 0, "No HTML detail pages generated under dirs/"


def test_smoke_produces_detail_pages(tmp_path):
    """At least one detail page (HTML) must be generated for the lbrn2 fixture."""
    run_cli(str(FILES_DIR), "--output-dir", str(tmp_path))
    dirs_root = tmp_path / "dirs"
    # shelf.lbrn2 should produce shelf.html
    detail_pages = list(dirs_root.rglob("shelf.html"))
    assert len(detail_pages) > 0, "No detail page generated for shelf.lbrn2"


def test_no_files_returns_error_code(tmp_path):
    """An empty directory should return exit code 2."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run_cli(str(empty))
    assert result.returncode == 2
    assert "No supported files" in result.stderr


def test_flat_directory_indexes_root_files(tmp_path):
    """Files directly in the scan root (no subdirectories) must produce a
    dirs/index.html page and a landing card with the correct data-labels so
    the type-filter buttons work."""
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(str(FILES_DIR / "testfile.stl"), str(src / "testfile.stl"))

    out = tmp_path / "out"
    result = run_cli(str(src), "--output-dir", str(out))
    assert result.returncode == 0, result.stderr

    # dirs/index.html must be generated — previously it was skipped for root
    assert (out / "dirs" / "index.html").exists(), \
        "dirs/index.html not generated for flat directory"

    # Landing page must contain a card whose data-labels includes stl so the
    # STL filter button actually shows something
    landing = (out / "index.html").read_text(encoding="utf-8")
    assert "stl" in landing, \
        "STL label missing from landing page — type filter would show 0 cards"


def test_mixed_layout_indexes_all_files(tmp_path):
    """Files at root level AND inside a subdirectory must all get detail pages."""
    src = tmp_path / "src"
    subdir = src / "models"
    subdir.mkdir(parents=True)

    # File directly in the scan root
    shutil.copy(str(FILES_DIR / "testfile.stl"), str(src / "root_file.stl"))
    # File one level deep
    shutil.copy(str(FILES_DIR / "princess_donut.stl"), str(subdir / "sub_file.stl"))

    out = tmp_path / "out"
    result = run_cli(str(src), "--output-dir", str(out))
    assert result.returncode == 0, result.stderr

    html_names = {p.name for p in (out / "dirs").rglob("*.html")}
    assert "root_file.html" in html_names, \
        "No detail page for file sitting directly in the scan root"
    assert "sub_file.html" in html_names, \
        "No detail page for file in subdirectory"
