from __future__ import annotations

import collections
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh, write_bytes


# ---------------------------------------------------------------------------
# 3MF detail extraction (ported from scripts/3mf_extract.py)
# ---------------------------------------------------------------------------

_NS = {
    "m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
    "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06",
}

_SLICER_LABELS = {
    "printer_model": "Printer model",
    "printer_variant": "Printer variant",
    "printer_technology": "Technology",
    "bed_type": "Bed type",
    "nozzle_diameter": "Nozzle diameter",
    "filament_type": "Filament type",
    "filament_diameter": "Filament diameter",
    "layer_height": "Layer height",
    "initial_layer_print_height": "First layer height",
    "sparse_infill_density": "Infill density",
    "sparse_infill_pattern": "Infill pattern",
    "wall_loops": "Wall loops",
    "top_shell_layers": "Top shell layers",
    "bottom_shell_layers": "Bottom shell layers",
    "enable_support": "Supports",
    "support_type": "Support type",
    "brim_type": "Brim type",
    "brim_width": "Brim width",
    "outer_wall_speed": "Outer wall speed",
    "inner_wall_speed": "Inner wall speed",
    "initial_layer_speed": "First layer speed",
    "travel_speed": "Travel speed",
}

_USEFUL_PROJECT_KEYS = list(_SLICER_LABELS.keys())


def _parse_transform(text: str | None) -> list[float]:
    if not text:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    vals = [float(x) for x in text.split()]
    return vals if len(vals) == 12 else [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]


def _apply_transform(v: tuple[float, float, float], t: list[float]) -> tuple[float, float, float]:
    a, b, c, d, e, f, g, h, i, j, k, l = t
    x, y, z = v
    return (a*x + b*y + c*z + j, d*x + e*y + f*z + k, g*x + h*y + i*z + l)


def _tri_area_and_vol(p1, p2, p3) -> tuple[float, float]:
    ax, ay, az = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
    bx, by, bz = p3[0]-p1[0], p3[1]-p1[1], p3[2]-p1[2]
    cx, cy, cz = ay*bz - az*by, az*bx - ax*bz, ax*by - ay*bx
    area = 0.5 * math.sqrt(cx*cx + cy*cy + cz*cz)
    vol = (p1[0]*(p2[1]*p3[2] - p2[2]*p3[1])
           - p1[1]*(p2[0]*p3[2] - p2[2]*p3[0])
           + p1[2]*(p2[0]*p3[1] - p2[1]*p3[0])) / 6.0
    return area, vol


def _compute_connectivity(vertices, triangles):
    parent = list(range(len(vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    edge_counts: collections.Counter = collections.Counter()
    area = vol = 0.0
    for v1, v2, v3 in triangles:
        p1, p2, p3 = vertices[v1], vertices[v2], vertices[v3]
        a, v = _tri_area_and_vol(p1, p2, p3)
        area += a; vol += v
        for ea, eb in ((v1, v2), (v2, v3), (v3, v1)):
            edge_counts[tuple(sorted((ea, eb)))] += 1
        union(v1, v2); union(v2, v3)

    components = len({find(i) for i in range(len(vertices))})
    histogram = collections.Counter(edge_counts.values())
    return {
        "surface_area_mm2": area,
        "volume_mm3": abs(vol),
        "unique_edges": len(edge_counts),
        "connected_components": components,
        "is_manifold": set(histogram.keys()) == {2},
    }


def extract_3mf_details(path: Path) -> dict:
    """Extract geometry metadata and slicer settings from a 3MF file."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()

            model_path = "3D/3dmodel.model"
            if model_path not in names:
                return {"error": "3D/3dmodel.model not found in package"}

            main_root = ET.fromstring(zf.read(model_path))
            unit = main_root.attrib.get("unit", "millimeter")

            # Package metadata
            pkg_meta: dict[str, str] = {}
            for entry in main_root.findall(".//m:metadata", _NS):
                key = entry.attrib.get("name")
                if key:
                    pkg_meta[key] = entry.text or ""

            # Build transform
            build_item = main_root.find(".//m:build/m:item", _NS)
            build_transform = _parse_transform(
                build_item.attrib.get("transform") if build_item is not None else None
            )

            # Resolve mesh model path (may be a component reference)
            mesh_path = model_path
            component = main_root.find(".//m:components/m:component", _NS)
            if component is not None:
                ref = component.attrib.get(
                    "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path"
                )
                if ref:
                    mesh_path = ref.lstrip("/")

            mesh_root = ET.fromstring(zf.read(mesh_path))
            raw_verts = [
                (float(v.attrib["x"]), float(v.attrib["y"]), float(v.attrib["z"]))
                for v in mesh_root.findall(".//m:vertex", _NS)
            ]
            triangles = [
                (int(t.attrib["v1"]), int(t.attrib["v2"]), int(t.attrib["v3"]))
                for t in mesh_root.findall(".//m:triangle", _NS)
            ]
            tfm_verts = [_apply_transform(v, build_transform) for v in raw_verts]

            def _bbox_size(verts):
                if not verts:
                    return [0.0, 0.0, 0.0]
                return [max(v[i] for v in verts) - min(v[i] for v in verts) for i in range(3)]

            size = _bbox_size(tfm_verts)

            connectivity = _compute_connectivity(tfm_verts, triangles) if triangles else {
                "surface_area_mm2": 0.0, "volume_mm3": 0.0,
                "unique_edges": 0, "connected_components": 0, "is_manifold": False,
            }

            def fmt(v):
                return f"{v:.2f}"

            # Slicer settings (Bambu / PrusaSlicer project files)
            slicer_settings: list[dict] = []
            if "Metadata/project_settings.config" in names:
                try:
                    ps = json.loads(zf.read("Metadata/project_settings.config"))
                    for key in _USEFUL_PROJECT_KEYS:
                        if key in ps:
                            slicer_settings.append({
                                "key": key,
                                "label": _SLICER_LABELS[key],
                                "value": str(ps[key]),
                            })
                except Exception:
                    pass

            # Object/part names from model_settings (Bambu)
            object_names: list[str] = []
            if "Metadata/model_settings.config" in names:
                try:
                    ms_root = ET.fromstring(
                        zf.read("Metadata/model_settings.config").decode("utf-8")
                    )
                    for obj in ms_root.findall("./object"):
                        for part in obj.findall("./part"):
                            for md in part.findall("./metadata"):
                                if md.attrib.get("key") == "name":
                                    name = md.attrib.get("value", "").strip()
                                    if name:
                                        object_names.append(name)
                except Exception:
                    pass

            sa_mm2 = connectivity["surface_area_mm2"]
            vol_mm3 = connectivity["volume_mm3"]

            return {
                "unit": unit,
                "package_metadata": pkg_meta,
                "triangle_count": len(triangles),
                "vertex_count": len(raw_verts),
                "unique_edges": connectivity["unique_edges"],
                "connected_components": connectivity["connected_components"],
                "is_manifold": connectivity["is_manifold"],
                "size_x_mm": fmt(size[0]),
                "size_y_mm": fmt(size[1]),
                "size_z_mm": fmt(size[2]),
                "size_x_in": fmt(size[0] / 25.4),
                "size_y_in": fmt(size[1] / 25.4),
                "size_z_in": fmt(size[2] / 25.4),
                "surface_area_mm2": fmt(sa_mm2),
                "surface_area_cm2": fmt(sa_mm2 / 100.0),
                "volume_mm3": fmt(vol_mm3),
                "volume_cm3": fmt(vol_mm3 / 1000.0),
                "slicer_settings": slicer_settings,
                "object_names": object_names,
                "error": "",
            }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


class ThreeMFPlugin:
    name = "3mf"
    extensions = {".3mf"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        thumb_root = getattr(self, "thumb_root", None)
        scan_root = getattr(self, "scan_root", None)
        thumb_path = thumbnail_path_for(path, thumb_root=thumb_root, scan_root=scan_root)
        error = ""

        if not thumbnail_is_fresh(path, thumb_path):
            try:
                with zipfile.ZipFile(path) as z:
                    preview_candidates = [
                        name for name in z.namelist()
                        if name.lower().startswith("metadata/")
                        and name.lower().endswith((".png", ".jpg"))
                    ]

                    if preview_candidates:
                        preview_candidates.sort(key=lambda x: ("plate" not in x.lower(), x))
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
