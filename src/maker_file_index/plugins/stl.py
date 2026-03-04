from __future__ import annotations

from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh
import pdb

class STLPlugin:
    name = "stl"

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".stl"

    def render_thumbnail(self, path: Path, thumb_path: Path) -> str:
        import subprocess

        proc = subprocess.run(
            [
                "openscad",
                "-o", str(thumb_path),
                "--imgsize=400,400",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # Return stderr text if it didn't produce a file
        if not thumb_path.exists():
            #print(proc.stderr or proc.stdout or "")
            #pdb.set_trace()
            return (proc.stderr or proc.stdout or "").strip()

        return ""

    def index(self, path: Path) -> IndexRecord:
        thumb_path = thumbnail_path_for(path)

        err = ""
        # Only render if missing
        #if not thumb_path.exists():
            #self.render_thumbnail(path, thumb_path)

        if not thumbnail_is_fresh(path, thumb_path):
            err = self.render_thumbnail(path, thumb_path)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path if thumb_path.exists() else Path(""),
            error=err,
        )

