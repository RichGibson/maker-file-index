from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for


def url_path(p: str) -> str:
    """
    Convert a filesystem-relative path to a browser-friendly URL path.
    Encodes spaces and special chars, keeps / separators.
    """
    p = str(p)
    return quote(p.replace(os.sep, "/"), safe="/")


def render_stl_thumbnail(stl_path: Path, thumb_path: Path) -> str:
    """
    Render an STL file to a PNG thumbnail using numpy-stl and matplotlib.
    Returns an error string on failure, or "" on success.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot
        from mpl_toolkits import mplot3d
        from stl import mesh

        your_mesh = mesh.Mesh.from_file(str(stl_path))

        figure = pyplot.figure(figsize=(4, 4))
        axes = figure.add_subplot(projection="3d")
        axes.add_collection3d(mplot3d.art3d.Poly3DCollection(your_mesh.vectors, alpha=0.7))

        scale = your_mesh.points.flatten()
        axes.auto_scale_xyz(scale, scale, scale)

        axes.set_axis_off()
        figure.tight_layout(pad=0)

        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        pyplot.savefig(str(thumb_path), dpi=100, bbox_inches="tight")
        pyplot.close(figure)
        return ""

    except Exception as e:
        return f"{type(e).__name__}: {e}"


class STLPlugin:
    name = "stl"

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".stl"

    def find_sidecar_image(self, stl_path: Path) -> Path | None:
        """
        Look for an existing preview image for this STL.
        Search order:
          1) same directory as STL
          2) ./files
          3) ./images

        Matches same stem: foo.stl -> foo.png/jpg/jpeg/webp
        """
        exts = (".png", ".jpg", ".jpeg", ".webp")
        roots = [stl_path.parent, stl_path.parent / "files", stl_path.parent / "images"]

        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            for ext in exts:
                p = root / f"{stl_path.stem}{ext}"
                if p.exists() and p.is_file():
                    return p
                p = root / f"{stl_path.stem}_thumbnail{ext}"
                if p.exists() and p.is_file():
                    return p

        return None

    def index(self, path: Path) -> IndexRecord:
        sidecar = self.find_sidecar_image(path)
        if sidecar is not None:
            return IndexRecord(
                path=path,
                directory=path.parent,
                notes="",
                thumbnail_path=sidecar.resolve(),
                error="",
            )

        thumb_path = thumbnail_path_for(path)
        error = ""
        if not thumb_path.exists():
            scan_root = getattr(self, "scan_root", None)
            rel = path.relative_to(scan_root) if scan_root else Path(path.parent.name) / path.name
            print(f"Creating thumbnail for {rel}")
            error = render_stl_thumbnail(path, thumb_path)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path.resolve() if thumb_path.exists() else Path(""),
            error=error,
        )
