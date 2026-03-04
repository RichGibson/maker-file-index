from __future__ import annotations
import zipfile
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, write_bytes, thumbnail_is_fresh


class ThreeMFPlugin:
    name = "3mf"
    extensions = {".3mf"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        thumb_path = Path("")

        try:
            with zipfile.ZipFile(path) as z:

                preview_candidates = []
                for name in z.namelist():
                    lower = name.lower()
                    if lower.startswith("metadata/") and lower.endswith((".png", ".jpg")):
                        preview_candidates.append(name)

                if preview_candidates:
                    # prefer plate images if available
                    preview_candidates.sort(key=lambda x: ("plate" not in x.lower(), x))
                    preview_name = preview_candidates[0]
                    #thumb_path = path.with_name(path.stem + "_thumbnail.png")
                    thumb_path=thumbnail_path_for(path)
                    if thumbnail_is_fresh(path, thumb_path):
                        return IndexRecord(
                            path=path,
                            directory=path.parent,
                            notes="",
                            thumbnail_path=thumb_path,
                            error="",
                        )
                    data = z.read(preview_name)
                    write_bytes(thumb_path, data, overwrite=True)

        except Exception as e:
            return IndexRecord(
                path=path,
                directory=path.parent,
                notes="",
                thumbnail_path=Path(""),
                error=str(e),
            )

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path,
            error="",
        )
