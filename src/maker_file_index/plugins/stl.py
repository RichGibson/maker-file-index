from __future__ import annotations

import math
import os
import struct
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import quote

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for


# ---------------------------------------------------------------------------
# STL detail extraction (ported from scripts/stl_extract.py)
# ---------------------------------------------------------------------------

Vec3 = tuple[float, float, float]
Face = tuple[Vec3, Vec3, Vec3]


def _detect_stl_format(path: Path) -> str:
    size = path.stat().st_size
    if size < 84:
        raise ValueError("File too small to be a valid STL.")
    with path.open("rb") as f:
        f.read(80)
        tri_bytes = f.read(4)
        if len(tri_bytes) != 4:
            raise ValueError("Could not read STL triangle count.")
        tri_count = struct.unpack("<I", tri_bytes)[0]
    if 84 + tri_count * 50 == size:
        return "binary"
    with path.open("rb") as f:
        start = f.read(512).lstrip()
    if start.lower().startswith(b"solid"):
        return "ascii"
    return "binary"


def _parse_binary_stl(path: Path) -> tuple[str, list[Face]]:
    faces: list[Face] = []
    with path.open("rb") as f:
        header = f.read(80)
        header_text = header.decode("ascii", errors="replace").strip("\x00").strip()
        tri_count = struct.unpack("<I", f.read(4))[0]
        for _ in range(tri_count):
            rec = f.read(50)
            if len(rec) != 50:
                raise ValueError("Unexpected end of file reading binary STL.")
            vals = struct.unpack("<12fH", rec)
            faces.append(((vals[3], vals[4], vals[5]),
                          (vals[6], vals[7], vals[8]),
                          (vals[9], vals[10], vals[11])))
    return header_text, faces


def _parse_ascii_stl(path: Path) -> tuple[str | None, list[Face]]:
    faces: list[Face] = []
    header_text: str | None = None
    current: list[Vec3] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            lo = s.lower()
            if lo.startswith("solid") and header_text is None:
                header_text = s[5:].strip() or None
            if lo.startswith("vertex"):
                parts = s.split()
                if len(parts) >= 4:
                    current.append((float(parts[1]), float(parts[2]), float(parts[3])))
                    if len(current) == 3:
                        faces.append(tuple(current))  # type: ignore[arg-type]
                        current = []
    return header_text, faces


def _triangle_area(v1: Vec3, v2: Vec3, v3: Vec3) -> float:
    ab = (v2[0]-v1[0], v2[1]-v1[1], v2[2]-v1[2])
    ac = (v3[0]-v1[0], v3[1]-v1[1], v3[2]-v1[2])
    cp = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
    return 0.5 * math.sqrt(cp[0]**2 + cp[1]**2 + cp[2]**2)


def _signed_tetra_volume(v1: Vec3, v2: Vec3, v3: Vec3) -> float:
    cp = (v2[1]*v3[2]-v2[2]*v3[1], v2[2]*v3[0]-v2[0]*v3[2], v2[0]*v3[1]-v2[1]*v3[0])
    return (v1[0]*cp[0] + v1[1]*cp[1] + v1[2]*cp[2]) / 6.0


def extract_stl_details(path: Path) -> dict:
    """Extract geometry metadata from an STL file for the detail page."""
    try:
        fmt = _detect_stl_format(path)
        if fmt == "binary":
            header_text, faces = _parse_binary_stl(path)
        else:
            header_text, faces = _parse_ascii_stl(path)

        if not faces:
            return {"error": "No triangles found in STL file."}

        vertex_index: dict[Vec3, int] = {}
        vertices: list[Vec3] = []
        indexed_faces: list[tuple[int, int, int]] = []
        min_x = min_y = min_z = float("inf")
        max_x = max_y = max_z = float("-inf")
        surface_area = 0.0
        signed_volume = 0.0

        for v1, v2, v3 in faces:
            for v in (v1, v2, v3):
                if v not in vertex_index:
                    vertex_index[v] = len(vertices)
                    vertices.append(v)
                min_x = min(min_x, v[0]); max_x = max(max_x, v[0])
                min_y = min(min_y, v[1]); max_y = max(max_y, v[1])
                min_z = min(min_z, v[2]); max_z = max(max_z, v[2])
            i1, i2, i3 = vertex_index[v1], vertex_index[v2], vertex_index[v3]
            indexed_faces.append((i1, i2, i3))
            surface_area += _triangle_area(v1, v2, v3)
            signed_volume += _signed_tetra_volume(v1, v2, v3)

        edge_counts: Counter[tuple[int,int]] = Counter()
        neighbors: dict[int, set[int]] = defaultdict(set)
        for i1, i2, i3 in indexed_faces:
            for a, b in ((i1,i2),(i2,i3),(i3,i1)):
                e = (a,b) if a < b else (b,a)
                edge_counts[e] += 1
                neighbors[a].add(b); neighbors[b].add(a)

        visited: set[int] = set()
        components = 0
        for start in range(len(vertices)):
            if start in visited:
                continue
            components += 1
            q: deque[int] = deque([start])
            visited.add(start)
            while q:
                cur = q.popleft()
                for nxt in neighbors[cur]:
                    if nxt not in visited:
                        visited.add(nxt); q.append(nxt)

        sx, sy, sz = max_x-min_x, max_y-min_y, max_z-min_z
        vol_mm3 = abs(signed_volume)

        def _fmt3(v: float) -> str:
            return f"{v:.2f}"

        return {
            "format": fmt,
            "header_text": header_text or "",
            "triangle_count": len(faces),
            "unique_vertices": len(vertices),
            "unique_edges": len(edge_counts),
            "connected_components": components,
            "is_manifold": all(c == 2 for c in edge_counts.values()),
            "size_x_mm": _fmt3(sx),
            "size_y_mm": _fmt3(sy),
            "size_z_mm": _fmt3(sz),
            "size_x_in": _fmt3(sx / 25.4),
            "size_y_in": _fmt3(sy / 25.4),
            "size_z_in": _fmt3(sz / 25.4),
            "surface_area_mm2": _fmt3(surface_area),
            "surface_area_cm2": _fmt3(surface_area / 100.0),
            "surface_area_in2": _fmt3(surface_area / (25.4**2)),
            "volume_mm3": _fmt3(vol_mm3),
            "volume_cm3": _fmt3(vol_mm3 / 1000.0),
            "volume_in3": _fmt3(vol_mm3 / (25.4**3)),
            "error": "",
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


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
