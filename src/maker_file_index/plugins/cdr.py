from __future__ import annotations

import io
import zipfile
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh, write_bytes


def _bmp_to_png(bmp_bytes: bytes) -> bytes:
    """Convert BMP bytes to PNG bytes using matplotlib (already a dependency)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    buf_in = io.BytesIO(bmp_bytes)
    img = mpimg.imread(buf_in, format="bmp")

    buf_out = io.BytesIO()
    fig, ax = plt.subplots()
    ax.imshow(img)
    ax.axis("off")
    fig.savefig(buf_out, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    buf_out.seek(0)
    return buf_out.read()


def _extract_preview(path: Path) -> bytes | None:
    """
    Try to extract a preview image from a CDR ZIP archive.
    Checks metadata/thumbnails/ for BMP files first, then falls back
    to any image file anywhere in the archive.
    """
    with zipfile.ZipFile(path) as z:
        names = z.namelist()

        # Primary: metadata/thumbnails/*.bmp (confirmed location)
        candidates = [
            n for n in names
            if n.lower().startswith("metadata/thumbnails")
            and n.lower().endswith(".bmp")
        ]

        # Fallback 1: any BMP in the archive
        if not candidates:
            candidates = [n for n in names if n.lower().endswith(".bmp")]

        # Fallback 2: any PNG/JPG in the archive
        if not candidates:
            candidates = [
                n for n in names
                if n.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

        if not candidates:
            return None

        candidates.sort(key=lambda x: (
            not x.lower().startswith("metadata/thumbnails"),
            x,
        ))
        return z.read(candidates[0])


class CDRPlugin:
    name = "cdr"
    extensions = {".cdr"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        thumb_root = getattr(self, "thumb_root", None)
        scan_root = getattr(self, "scan_root", None)
        thumb_path = thumbnail_path_for(path, thumb_root=thumb_root, scan_root=scan_root)
        error = ""

        if not thumbnail_is_fresh(path, thumb_path):
            try:
                raw = _extract_preview(path)
                if raw is not None:
                    # Convert BMP to PNG; fall back to saving raw bytes on error
                    if raw[:2] == b"BM":
                        try:
                            png_bytes = _bmp_to_png(raw)
                            write_bytes(thumb_path, png_bytes)
                        except Exception:
                            # Save as BMP with correct extension if conversion fails
                            bmp_path = thumb_path.with_suffix(".bmp")
                            write_bytes(bmp_path, raw)
                            thumb_path = bmp_path
                    else:
                        write_bytes(thumb_path, raw)
            except zipfile.BadZipFile:
                error = "Not a ZIP-based CDR file (older format not supported)"
            except Exception as e:
                error = str(e)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path if thumb_path.exists() else Path(""),
            error=error,
        )
