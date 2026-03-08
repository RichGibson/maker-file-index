from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh


# ---------------------------------------------------------------------------
# DXF detail extraction (ported from scripts/dxf_extract.py)
# ---------------------------------------------------------------------------

_PAIR_RE = re.compile(r"^\s*(-?\d+)\s*$")

_ACAD_VERSIONS = {
    "AC1006": "R10", "AC1009": "R11/R12", "AC1012": "R13", "AC1014": "R14",
    "AC1015": "2000", "AC1018": "2004", "AC1021": "2007", "AC1024": "2010",
    "AC1027": "2013", "AC1032": "2018",
}


def _pairs(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    result = []
    i = 0
    while i + 1 < len(lines):
        m = _PAIR_RE.match(lines[i])
        if m:
            result.append((int(m.group(1)), lines[i + 1].rstrip("\n\r")))
        i += 2
    return result


def _f(v: str) -> float | None:
    try:
        return float(v.strip())
    except Exception:
        return None


def _i(v: str) -> int | None:
    try:
        return int(v.strip())
    except Exception:
        return None


def _entity_length(etype: str, data: dict) -> float | None:
    etype = etype.upper()
    if etype == "LINE":
        x1 = _f(data.get(10, ["0"])[0]) or 0.0
        y1 = _f(data.get(20, ["0"])[0]) or 0.0
        z1 = _f(data.get(30, ["0"])[0]) or 0.0
        x2 = _f(data.get(11, ["0"])[0]) or 0.0
        y2 = _f(data.get(21, ["0"])[0]) or 0.0
        z2 = _f(data.get(31, ["0"])[0]) or 0.0
        return math.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)
    if etype in {"LWPOLYLINE", "POLYLINE"}:
        xs = [_f(v) for v in data.get(10, [])]
        ys = [_f(v) for v in data.get(20, [])]
        pts = [(_x or 0.0, _y or 0.0) for _x, _y in zip(xs, ys)]
        if len(pts) < 2:
            return 0.0
        total = sum(math.hypot(pts[k+1][0]-pts[k][0], pts[k+1][1]-pts[k][1]) for k in range(len(pts)-1))
        flags = _i(data.get(70, ["0"])[0]) or 0
        if flags & 1:
            total += math.hypot(pts[-1][0]-pts[0][0], pts[-1][1]-pts[0][1])
        return total
    if etype == "CIRCLE":
        r = _f(data.get(40, ["0"])[0]) or 0.0
        return 2 * math.pi * r
    if etype == "ARC":
        r = _f(data.get(40, ["0"])[0]) or 0.0
        start = math.radians(_f(data.get(50, ["0"])[0]) or 0.0)
        end = math.radians(_f(data.get(51, ["0"])[0]) or 0.0)
        delta = end - start
        if delta < 0:
            delta += 2 * math.pi
        return r * delta
    if etype == "ELLIPSE":
        mx = _f(data.get(11, ["0"])[0]) or 0.0
        my = _f(data.get(21, ["0"])[0]) or 0.0
        ratio = _f(data.get(40, ["1"])[0]) or 1.0
        a = math.hypot(mx, my)
        b = a * ratio
        if a == 0 or b == 0:
            return 0.0
        full = math.pi * (3*(a+b) - math.sqrt((3*a+b)*(a+3*b)))
        start = _f(data.get(41, ["0"])[0]) or 0.0
        end = _f(data.get(42, [str(2*math.pi)])[0]) or (2*math.pi)
        span = end - start
        if span < 0:
            span += 2 * math.pi
        return full * (span / (2*math.pi))
    return None


def _update_bounds(bounds: dict, x: float, y: float, z: float = 0.0) -> None:
    for key, val in (("min_x", x), ("max_x", x), ("min_y", y), ("max_y", y), ("min_z", z), ("max_z", z)):
        cur = bounds[key]
        if cur is None or ("min" in key and val < cur) or ("max" in key and val > cur):
            bounds[key] = val


def _collect_bounds(etype: str, data: dict, bounds: dict) -> None:
    for xc, yc, zc in ((10,20,30),(11,21,31),(12,22,32),(13,23,33)):
        for idx in range(min(len(data.get(xc,[])), len(data.get(yc,[])))):
            x = _f(data[xc][idx]); y = _f(data[yc][idx])
            z = _f(data[zc][idx]) if idx < len(data.get(zc,[])) else 0.0
            if x is not None and y is not None:
                _update_bounds(bounds, x, y, z or 0.0)
    eu = etype.upper()
    if eu in {"CIRCLE", "ARC"}:
        cx = _f(data.get(10,["0"])[0]) or 0.0
        cy = _f(data.get(20,["0"])[0]) or 0.0
        cz = _f(data.get(30,["0"])[0]) or 0.0
        r  = _f(data.get(40,["0"])[0]) or 0.0
        _update_bounds(bounds, cx-r, cy-r, cz)
        _update_bounds(bounds, cx+r, cy+r, cz)
    if eu == "ELLIPSE":
        cx = _f(data.get(10,["0"])[0]) or 0.0
        cy = _f(data.get(20,["0"])[0]) or 0.0
        cz = _f(data.get(30,["0"])[0]) or 0.0
        mx = _f(data.get(11,["0"])[0]) or 0.0
        my = _f(data.get(21,["0"])[0]) or 0.0
        ratio = _f(data.get(40,["1"])[0]) or 1.0
        a = math.hypot(mx, my); b = a * ratio
        _update_bounds(bounds, cx-a, cy-b, cz)
        _update_bounds(bounds, cx+a, cy+b, cz)


def extract_dxf_details(path: Path) -> dict:
    """Extract metadata and geometry from a DXF file."""
    try:
        raw = path.read_bytes()
        if b"\x00" in raw[:1024]:
            return {"error": "Binary DXF files are not supported by the detail extractor."}

        text = raw.decode("latin-1", errors="replace")
        ps = _pairs(text)

        current_section = None
        layers: list[dict] = []
        texts: list[str] = []
        entity_counts: Counter = Counter()
        entities_by_layer: Counter = Counter()
        length_by_type: defaultdict = defaultdict(float)
        bounds = {k: None for k in ("min_x","max_x","min_y","max_y","min_z","max_z")}
        header: dict = {}
        i = 0

        while i < len(ps):
            code, value = ps[i]

            if code == 0 and value == "SECTION" and i+1 < len(ps) and ps[i+1][0] == 2:
                current_section = ps[i+1][1].strip()
                i += 2; continue

            if code == 0 and value == "ENDSEC":
                current_section = None; i += 1; continue

            if current_section == "HEADER" and code == 9:
                var = value.strip()
                coords: list[float] = []
                j = i + 1
                while j < len(ps):
                    c2, v2 = ps[j]
                    if c2 == 9 or (c2 == 0 and v2 in {"ENDSEC","SECTION"}):
                        break
                    n = _f(v2)
                    if n is not None and c2 in {10,20,30,40,50,70}:
                        coords.append(n)
                    elif c2 in {1,3}:
                        header[var] = v2.strip()
                    j += 1
                if coords:
                    header[var] = coords if len(coords) > 1 else coords[0]
                i = j; continue

            if current_section == "TABLES" and code == 0 and value == "LAYER":
                layer: dict = {}
                j = i + 1
                while j < len(ps):
                    c2, v2 = ps[j]
                    if c2 == 0: break
                    if c2 == 2: layer["name"] = v2.strip()
                    elif c2 == 62: layer["color"] = _i(v2)
                    elif c2 == 6: layer["linetype"] = v2.strip()
                    j += 1
                if layer.get("name"):
                    layers.append(layer)
                i = j; continue

            if current_section == "ENTITIES" and code == 0:
                etype = value.strip()
                edata: dict = defaultdict(list)
                j = i + 1
                while j < len(ps):
                    c2, v2 = ps[j]
                    if c2 == 0: break
                    edata[c2].append(v2)
                    j += 1

                entity_counts[etype] += 1
                layer_name = edata.get(8, ["0"])[0].strip()
                entities_by_layer[layer_name] += 1
                _collect_bounds(etype, edata, bounds)

                if etype in {"TEXT","MTEXT","ATTRIB","ATTDEF"}:
                    if etype == "MTEXT":
                        raw_text = "".join(edata.get(1,[]) + edata.get(3,[]))
                    else:
                        raw_text = "".join(edata.get(1,[]))
                    cleaned = raw_text.replace("\\P", "\n").strip()
                    if cleaned:
                        texts.append(cleaned)

                length = _entity_length(etype, edata)
                if length is not None:
                    length_by_type[etype] += length

                i = j; continue

            i += 1

        # Dimensions from bounds
        def _dim(a, b):
            return f"{b - a:.2f}" if a is not None and b is not None else ""

        acad_ver = header.get("$ACADVER", "")
        ver_name = _ACAD_VERSIONS.get(acad_ver, "")

        total_length = sum(length_by_type.values())

        return {
            "acad_version": acad_ver,
            "acad_version_name": ver_name,
            "size_x": _dim(bounds["min_x"], bounds["max_x"]),
            "size_y": _dim(bounds["min_y"], bounds["max_y"]),
            "size_z": _dim(bounds["min_z"], bounds["max_z"]),
            "total_entities": sum(entity_counts.values()),
            "entity_counts": dict(sorted(entity_counts.items(), key=lambda kv: -kv[1])),
            "entities_by_layer": dict(sorted(entities_by_layer.items(), key=lambda kv: -kv[1])),
            "layers": layers,
            "total_length": f"{total_length:.2f}" if total_length else "",
            "length_by_type": {k: f"{v:.2f}" for k, v in sorted(length_by_type.items(), key=lambda kv: -kv[1])},
            "texts": sorted(set(texts))[:30],
            "error": "",
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


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
        thumb_root = getattr(self, "thumb_root", None)
        scan_root = getattr(self, "scan_root", None)
        thumb_path = thumbnail_path_for(path, thumb_root=thumb_root, scan_root=scan_root)
        error = ""
        if not thumbnail_is_fresh(path, thumb_path):
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
