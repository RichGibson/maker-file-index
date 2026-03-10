"""CLI smoke tests — run maker-file-index against the sample files/ directory."""
from __future__ import annotations

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
