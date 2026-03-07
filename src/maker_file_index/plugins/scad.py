from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh


def render_scad_thumbnail(scad_path: Path, thumb_path: Path) -> str:
    """
    Render a SCAD file to a PNG thumbnail using the OpenSCAD CLI.
    Returns an error string on failure, or "" on success.
    """
    openscad = shutil.which("openscad")
    if not openscad:
        return "openscad not found in PATH"

    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                openscad,
                "--export-format", "png",
                "--autocenter",
                "--viewall",
                "-o", str(thumb_path),
                str(scad_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return result.stderr.strip() or f"openscad exited with code {result.returncode}"
        if not thumb_path.exists():
            return "openscad ran but produced no output file"
        return ""
    except subprocess.TimeoutExpired:
        return "openscad timed out after 60s"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


class SCADPlugin:
    name = "scad"

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".scad"

    def index(self, path: Path) -> IndexRecord:
        thumb_path = thumbnail_path_for(path)
        error = ""
        if not thumbnail_is_fresh(path, thumb_path):
            scan_root = getattr(self, "scan_root", None)
            rel = path.relative_to(scan_root) if scan_root else Path(path.parent.name) / path.name
            print(f"Creating thumbnail for {rel}")
            error = render_scad_thumbnail(path, thumb_path)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path.resolve() if thumb_path.exists() else Path(""),
            error=error,
        )
