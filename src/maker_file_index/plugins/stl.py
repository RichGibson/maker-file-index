from __future__ import annotations

from pathlib import Path

from maker_file_index.model import IndexRecord


class STLPlugin:
    name = "stl"

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".stl"

    def index(self, path: Path) -> IndexRecord:
        # placeholder — no thumbnail yet
        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=Path(""),
            error="",
        )
