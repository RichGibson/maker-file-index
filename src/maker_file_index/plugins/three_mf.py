from __future__ import annotations
import zipfile
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, write_bytes


class ThreeMFPlugin:
    name = "3mf"
    extensions = {".3mf"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        thumb_path = thumbnail_path_for(path)
        error = ""

        if not thumb_path.exists():
            try:
                with zipfile.ZipFile(path) as z:
                    preview_candidates = [
                        name for name in z.namelist()
                        if name.lower().startswith("metadata/")
                        and name.lower().endswith((".png", ".jpg"))
                    ]

                    if preview_candidates:
                        preview_candidates.sort(key=lambda x: ("plate" not in x.lower(), x))
                        scan_root = getattr(self, "scan_root", None)
                        rel = path.relative_to(scan_root) if scan_root else Path(path.parent.name) / path.name
                        print(f"Extracting thumbnail for {rel}")
                        data = z.read(preview_candidates[0])
                        write_bytes(thumb_path, data)

            except Exception as e:
                error = str(e)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path if thumb_path.exists() else Path(""),
            error=error,
        )
