from __future__ import annotations

from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for


def render_dxf_thumbnail(dxf_path: Path, thumb_path: Path) -> str:
    """
    Render a DXF file to a PNG thumbnail using ezdxf + matplotlib.
    Returns an error string on failure, or "" on success.
    """
    try:
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        fig = plt.figure(figsize=(6, 6))
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp, finalize=True)

        ax.set_axis_off()
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(thumb_path), dpi=100, bbox_inches="tight")
        plt.close(fig)
        return ""

    except Exception as e:
        return f"{type(e).__name__}: {e}"


class DXFPlugin:
    name = "dxf"
    extensions = {".dxf"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        thumb_path = thumbnail_path_for(path)
        error = ""
        if not thumb_path.exists():
            scan_root = getattr(self, "scan_root", None)
            rel = path.relative_to(scan_root) if scan_root else Path(path.parent.name) / path.name
            print(f"Creating thumbnail for {rel}")
            error = render_dxf_thumbnail(path, thumb_path)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path if thumb_path.exists() else Path(""),
            error=error,
        )
