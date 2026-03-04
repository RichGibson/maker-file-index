from __future__ import annotations

from pathlib import Path

from maker_file_index.model import IndexRecord


class ThreeMFPlugin:
    name = "3mf"
    extensions = {".3mf"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=Path(""),
            error="",
        )
