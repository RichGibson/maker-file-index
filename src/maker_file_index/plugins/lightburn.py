from __future__ import annotations

import base64
import binascii
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from maker_file_index.plugins.base import FilePlugin
from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh, write_bytes

_VERTEX_RE = re.compile(r"V([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_PRIM_RE = re.compile(r"([LB])(\d+)\s+(\d+)")


def _parse_transform(text: str | None) -> tuple:
    if not text:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    values = [float(p) for p in text.split()]
    return tuple(values) if len(values) == 6 else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _apply_transform(point: tuple, xform: tuple) -> tuple:
    a, b, c, d, e, f = xform
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def _parse_vertices(text: str | None) -> list:
    if not text:
        return []
    return [(float(m.group(1)), float(m.group(2))) for m in _VERTEX_RE.finditer(text)]


def _parse_primitives(text: str | None) -> list:
    if not text:
        return []
    return [(kind, int(s), int(e)) for kind, s, e in _PRIM_RE.findall(text)]


def _bezier_length(p0, p1, p2, p3, steps: int = 24) -> float:
    def pt(t):
        u = 1.0 - t
        return (
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        )
    pts = [pt(i / steps) for i in range(steps + 1)]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _shape_path_length(shape_el: ET.Element) -> float:
    xform = _parse_transform(shape_el.findtext("XForm"))
    verts = [_apply_transform(v, xform) for v in _parse_vertices(shape_el.findtext("VertList"))]
    prims = _parse_primitives((shape_el.findtext("PrimList") or "").strip())

    if not verts:
        return 0.0
    if not prims:
        return sum(math.dist(a, b) for a, b in zip(verts, verts[1:]))

    length = 0.0
    i = 0
    while i < len(prims):
        kind, start, end = prims[i]
        if kind == "L":
            if start < len(verts) and end < len(verts):
                length += math.dist(verts[start], verts[end])
            i += 1
        elif kind == "B":
            # Collect contiguous bezier chain
            chain = [prims[i]]
            j = i + 1
            while j < len(prims) and prims[j][0] == "B":
                chain.append(prims[j])
                j += 1
            if len(chain) >= 3:
                k = 0
                while k + 2 < len(chain):
                    a, b, c = chain[k], chain[k + 1], chain[k + 2]
                    if (a[2] == a[1] + 1 and b[1] == a[2] and c[1] == b[2]
                            and c[2] == c[1] + 1 and c[2] < len(verts)):
                        length += _bezier_length(verts[a[1]], verts[a[2]], verts[b[2]], verts[c[2]])
                        k += 3
                    else:
                        if a[1] < len(verts) and a[2] < len(verts):
                            length += math.dist(verts[a[1]], verts[a[2]])
                        k += 1
                while k < len(chain):
                    seg = chain[k]
                    if seg[1] < len(verts) and seg[2] < len(verts):
                        length += math.dist(verts[seg[1]], verts[seg[2]])
                    k += 1
            else:
                for seg in chain:
                    if seg[1] < len(verts) and seg[2] < len(verts):
                        length += math.dist(verts[seg[1]], verts[seg[2]])
            i = j
        else:
            i += 1
    return length


def _fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(int(mins), 60)
    if hours:
        return f"{hours}h {mins}m {secs:.0f}s"
    return f"{int(mins)}m {secs:.0f}s"


LIKELY_EXTS = {".lbrn2", ".lbrn"}

# LightBurn's standard 30-slot layer color palette (indexed by layer number)
LIGHTBURN_PALETTE = [
    "#000000", "#0000ff", "#ff0000", "#00cc00", "#ff9900", "#cc00cc",
    "#00cccc", "#ffff00", "#ff7700", "#007700", "#0099ff", "#ff0099",
    "#9900ff", "#996633", "#999999", "#003399", "#ff6600", "#006600",
    "#6699ff", "#ff9999", "#cc99ff", "#cc9966", "#cccccc", "#336699",
    "#ffcc00", "#009933", "#99ccff", "#ff66cc", "#cc66ff", "#ccaa77",
]


def _layer_color(index: int) -> str:
    try:
        return LIGHTBURN_PALETTE[int(index) % len(LIGHTBURN_PALETTE)]
    except (ValueError, TypeError):
        return "#888888"


def _text_color_for(bg_hex: str) -> str:
    """Return white or near-black depending on background luminance."""
    r = int(bg_hex[1:3], 16)
    g = int(bg_hex[3:5], 16)
    b = int(bg_hex[5:7], 16)
    return "#ffffff" if (0.299 * r + 0.587 * g + 0.114 * b) < 140 else "#222222"


def is_likely_lightburn_project(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in LIKELY_EXTS

def _find_thumbnail_b64(root: ET.Element) -> str:
    for thumb in root.iter("Thumbnail"):
        b64 = (thumb.attrib.get("Source") or "").strip()
        if b64:
            return b64

        if thumb.text and thumb.text.strip():
            return thumb.text.strip()

        src = thumb.find("Source")
        if src is not None and src.text and src.text.strip():
            return src.text.strip()

    raise ValueError("No thumbnail found. Expected a <Thumbnail> element with base64 data.")


def _decode_b64(data_b64: str) -> bytes:
    data_b64 = "".join(data_b64.split())
    pad = (-len(data_b64)) % 4
    if pad:
        data_b64 += "=" * pad
    try:
        return base64.b64decode(data_b64, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Thumbnail base64 decode failed: {e}") from e


def _sniff_extension(blob: bytes) -> str:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith(b"GIF87a") or blob.startswith(b"GIF89a"):
        return ".gif"
    if blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def extract_thumbnail(input_path: Path, output_path: Path | None = None, overwrite: bool = False) -> Path:
    tree = ET.parse(input_path)
    root = tree.getroot()

    b64 = _find_thumbnail_b64(root)
    blob = _decode_b64(b64)

    if output_path is None:
        ext = _sniff_extension(blob)
        output_path = input_path.with_name(f"{input_path.stem}_thumbnail{ext}")

    #if output_path.exists() and not overwrite:
        #raise FileExistsError(f"Output file already exists: {output_path} (use overwrite=True)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(blob)
    return output_path

def extract_notes_and_thumbnail(path: Path, *, thumb_root: Path | None = None, scan_root: Path | None = None) -> IndexRecord:
    """
    Returns Notes (blank if missing) and writes/returns the extracted thumbnail path if present.
    Supports:
      <Notes>text</Notes>
      <Notes Notes="text with &#10; newlines" />
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        notes_el = root.find(".//Notes")
        notes_text = ""
        if notes_el is not None:
            attr_val = (notes_el.attrib.get("Notes") or "").strip()
            if attr_val:
                notes_text = attr_val
            else:
                notes_text = (notes_el.text or "").strip()

        notes_text = notes_text.replace("\r\n", "\n").replace("\r", "\n").strip()

        thumb_path = Path("")
        try:
            expected = thumbnail_path_for(path, thumb_root=thumb_root, scan_root=scan_root)
            if not thumbnail_is_fresh(path, expected):
                extract_thumbnail(path, output_path=expected)
            thumb_path = expected
        except Exception:
            thumb_path = Path("")

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes=notes_text,
            thumbnail_path=thumb_path,
            error="",
        )

    except ET.ParseError as e:
        return IndexRecord(
            path=path,
            directory=path.parent,
            notes=notes_text,
            thumbnail_path=thumb_path,
            error="",
        )
    except Exception as e:
        return IndexRecord(
            path=path,
            directory=path.parent,
            notes=notes_text,
            thumbnail_path=thumb_path,
            error="",
        )


# ---------------------------------------------------------------------------
# Improved time estimation (ported from scripts/lightburn_estimate_time_3.py)
# ---------------------------------------------------------------------------

_VERT_RE2 = re.compile(r"V(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)")
_MATRIX_RE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$"
)

# Defaults for estimation parameters
_TRAVEL_SPEED = 200.0        # mm/s
_PATH_OVERHEAD = 0.12        # seconds per path start
_CORNER_OVERHEAD = 0.03      # seconds per sharp corner
_SHORT_SEG_THRESHOLD = 3.0   # mm — segments shorter than this are penalised
_SHORT_SEG_PENALTY = 0.45    # penalty factor for short segments
_RASTER_EFFICIENCY = 0.70    # fraction of nominal speed used for raster


@dataclass
class _CutSetting:
    index: int
    name: str
    layer_type: str
    speed: float | None
    num_passes: int = 1
    do_output: bool = True
    interval: float | None = None
    overscan: float | None = None
    scan_opt: str | None = None


@dataclass
class _VectorStats:
    cut_length_mm: float = 0.0
    travel_mm: float = 0.0
    num_paths: int = 0
    num_corners: int = 0
    time_seconds: float = 0.0


@dataclass
class _RasterStats:
    scan_gap_mm: float = 0.1
    overscan_mm: float = 0.0
    scan_lines: int = 0
    scan_distance_mm: float = 0.0
    time_seconds: float = 0.0
    num_objects: int = 0


@dataclass
class _LayerEst:
    cut_index: int
    name: str
    layer_type: str
    speed: float | None
    num_passes: int
    do_output: bool
    vector: _VectorStats = field(default_factory=_VectorStats)
    raster: _RasterStats = field(default_factory=_RasterStats)


def _lb_try_float(v: str | None) -> float | None:
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _lb_try_int(v: str | None, default: int = 0) -> int:
    try:
        return int(float(v)) if v is not None else default
    except ValueError:
        return default


def _lb_parse_cut_settings(root: ET.Element) -> dict[int, _CutSetting]:
    settings: dict[int, _CutSetting] = {}
    for cut in root.findall("CutSetting"):
        values = {child.tag: child.attrib.get("Value") for child in cut}
        idx = _lb_try_int(values.get("index"), -1)
        if idx < 0:
            continue
        settings[idx] = _CutSetting(
            index=idx,
            name=values.get("name") or f"Layer {idx}",
            layer_type=cut.attrib.get("type", "Cut"),
            speed=_lb_try_float(values.get("speed")),
            num_passes=max(1, _lb_try_int(values.get("numPasses"), 1)),
            do_output=values.get("doOutput", "1") != "0",
            interval=_lb_try_float(values.get("interval")),
            overscan=_lb_try_float(values.get("overscan")),
            scan_opt=values.get("scanOpt"),
        )
    return settings


def _lb_parse_points(elem: ET.Element) -> list[tuple[float, float]]:
    vert_text = elem.findtext("VertList") or ""
    xform_text = (elem.findtext("XForm") or "").strip()
    m = _MATRIX_RE.match(xform_text)
    if m:
        a, b, c, d, tx, ty = (float(g) for g in m.groups())
    else:
        a, b, c, d, tx, ty = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
    points = []
    for match in _VERT_RE2.finditer(vert_text):
        x, y = float(match.group("x")), float(match.group("y"))
        points.append((a * x + c * y + tx, b * x + d * y + ty))
    return points


def _lb_same_pt(p1: tuple, p2: tuple, tol: float = 1e-6) -> bool:
    return abs(p1[0] - p2[0]) <= tol and abs(p1[1] - p2[1]) <= tol


def _lb_path_closed(shape: ET.Element, pts: list) -> bool:
    prim = (shape.findtext("PrimList") or "").lower()
    if "closed" in prim:
        return True
    return len(pts) >= 2 and _lb_same_pt(pts[0], pts[-1])


def _lb_polyline_length(pts: list, closed: bool) -> float:
    if len(pts) < 2:
        return 0.0
    total = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if closed and not _lb_same_pt(pts[0], pts[-1]):
        total += math.dist(pts[-1], pts[0])
    return total


def _lb_count_corners(pts: list, closed: bool, threshold: float = 150.0) -> int:
    if len(pts) < 3:
        return 0
    count = 0
    ring = pts[:-1] if (closed and _lb_same_pt(pts[0], pts[-1])) else pts
    n = len(ring)
    indices = range(n) if closed else range(1, n - 1)
    for i in indices:
        prev = ring[(i - 1) % n]
        curr = ring[i]
        nxt = ring[(i + 1) % n]
        ax, ay = curr[0] - prev[0], curr[1] - prev[1]
        bx, by = nxt[0] - curr[0], nxt[1] - curr[1]
        ma, mb = math.hypot(ax, ay), math.hypot(bx, by)
        if ma < 1e-9 or mb < 1e-9:
            continue
        dot = max(-1.0, min(1.0, (ax * bx + ay * by) / (ma * mb)))
        if math.degrees(math.acos(dot)) < threshold:
            count += 1
    return count


def _lb_vector_path_time(pts: list, closed: bool, speed: float) -> tuple[float, int]:
    pairs = list(zip(pts, pts[1:]))
    if closed and not _lb_same_pt(pts[0], pts[-1]):
        pairs.append((pts[-1], pts[0]))
    total, short = 0.0, 0
    for p1, p2 in pairs:
        seg = math.dist(p1, p2)
        if seg <= 0:
            continue
        eff = speed * _SHORT_SEG_PENALTY if seg < _SHORT_SEG_THRESHOLD else speed
        total += seg / max(eff, 1e-9)
        if seg < _SHORT_SEG_THRESHOLD:
            short += 1
    return total, short


def _lb_is_raster(setting: _CutSetting) -> bool:
    if setting.interval is not None or setting.scan_opt or setting.overscan is not None:
        return True
    n = setting.name.lower()
    if any(k in n for k in ("interval", "scan", "fill")):
        return True
    t = setting.layer_type.lower()
    return any(k in t for k in ("fill", "image", "scan"))


def _lb_raster_efficiency(setting: _CutSetting) -> float:
    scan_opt = (setting.scan_opt or "").strip().lower()
    if scan_opt == "individual":
        return min(_RASTER_EFFICIENCY, 0.60)
    if scan_opt in {"bi", "bidirectional"}:
        return max(_RASTER_EFFICIENCY, 0.75)
    return _RASTER_EFFICIENCY


def _lb_bbox(pts: list) -> tuple | None:
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _lb_bbox_union(a: tuple | None, b: tuple | None) -> tuple | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _lb_estimate_job(root: ET.Element) -> dict[int, _LayerEst]:
    settings = _lb_parse_cut_settings(root)
    estimates: dict[int, _LayerEst] = {}
    raster_bboxes: dict[int, tuple | None] = {}
    prev_end: tuple | None = None

    def _get_layer(setting: _CutSetting) -> _LayerEst:
        if setting.index not in estimates:
            estimates[setting.index] = _LayerEst(
                cut_index=setting.index,
                name=setting.name,
                layer_type=setting.layer_type,
                speed=setting.speed,
                num_passes=setting.num_passes,
                do_output=setting.do_output,
            )
        return estimates[setting.index]

    for shape in root.iter("Shape"):
        ci = _lb_try_int(shape.attrib.get("CutIndex"), -1)
        if ci < 0:
            continue
        setting = settings.get(ci) or _CutSetting(index=ci, name=f"Layer {ci}", layer_type="Unknown", speed=None)
        if not setting.do_output:
            continue

        speed = setting.speed  # LightBurn stores speed in mm/s
        shape_type = (shape.attrib.get("Type") or "").strip()
        raster_like = _lb_is_raster(setting) or shape_type in {"Text", "Image"}

        if raster_like:
            backup = shape.find("BackupPath")
            pts = _lb_parse_points(backup) if backup is not None else []
            if not pts:
                pts = _lb_parse_points(shape)
            bbox = _lb_bbox(pts)
            if bbox is not None:
                raster_bboxes[ci] = _lb_bbox_union(raster_bboxes.get(ci), bbox)
                if speed:
                    layer = _get_layer(setting)
                    scan_gap = setting.interval if setting.interval is not None else 0.1
                    overscan = setting.overscan if setting.overscan is not None else 0.0
                    eff = _lb_raster_efficiency(setting)
                    min_x, min_y, max_x, max_y = bbox
                    w, h = max(0.0, max_x - min_x), max(0.0, max_y - min_y)
                    lines = max(1, math.ceil(h / max(scan_gap, 1e-9)))
                    dist = lines * (w + 2.0 * overscan)
                    layer.raster.num_objects += 1
                    layer.raster.scan_lines += lines
                    layer.raster.scan_distance_mm += dist
                    layer.raster.scan_gap_mm = scan_gap
                    layer.raster.overscan_mm = overscan
            continue

        if shape_type != "Path":
            continue
        pts = _lb_parse_points(shape)
        if len(pts) < 2:
            continue

        layer = _get_layer(setting)
        closed = _lb_path_closed(shape, pts)
        length = _lb_polyline_length(pts, closed)
        corners = _lb_count_corners(pts, closed)
        layer.vector.cut_length_mm += length
        layer.vector.num_paths += 1
        layer.vector.num_corners += corners
        if prev_end is not None:
            layer.vector.travel_mm += math.dist(prev_end, pts[0])
        prev_end = pts[0] if closed else pts[-1]

        if speed:
            seg_time, _ = _lb_vector_path_time(pts, closed, speed)
            layer.vector.time_seconds += seg_time

    # Finalise per-layer totals
    for ci, layer in estimates.items():
        setting = settings.get(ci)
        passes = setting.num_passes if setting else 1
        travel_t = layer.vector.travel_mm / max(_TRAVEL_SPEED, 1e-9)
        path_t = layer.vector.num_paths * _PATH_OVERHEAD
        corner_t = layer.vector.num_corners * _CORNER_OVERHEAD
        layer.vector.time_seconds = (layer.vector.time_seconds + travel_t + path_t + corner_t) * passes
        layer.raster.time_seconds = (
            layer.raster.scan_distance_mm / max((layer.speed or 0) * _lb_raster_efficiency(setting or _CutSetting(ci, "", "", None)), 1e-9)
            if layer.raster.scan_lines and layer.speed
            else 0.0
        ) * passes

    return estimates


def extract_lightburn_details(path: Path) -> dict:
    """
    Extract rich metadata from a LightBurn file for a detail page.
    Returns a dict with app_version, device_name, notes, layers, shape_counts, text_strings.
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        return {}

    app_version = root.attrib.get("AppVersion", "")
    device_name = root.attrib.get("DeviceName", "")
    material_height = root.attrib.get("MaterialHeight", "")
    mirror_x = root.attrib.get("MirrorX", "")
    mirror_y = root.attrib.get("MirrorY", "")
    format_version = root.attrib.get("FormatVersion", "")

    notes_el = root.find(".//Notes")
    notes = ""
    if notes_el is not None:
        notes = (notes_el.attrib.get("Notes") or notes_el.text or "").strip()
        notes = notes.replace("\r\n", "\n").replace("\r", "\n")

    layers = []
    for cs in root.findall("CutSetting"):
        data = {c.tag: c.attrib.get("Value", "") for c in cs}
        try:
            idx = int(data.get("index", "0"))
        except ValueError:
            idx = 0
        color = _layer_color(idx)
        layers.append({
            "index": data.get("index", "?"),
            "name": data.get("name", ""),
            "type": cs.attrib.get("type", ""),
            "speed": data.get("speed", ""),
            "min_power": data.get("minPower", ""),
            "max_power": data.get("maxPower", ""),
            "passes": data.get("numPasses", "1"),
            "do_output": data.get("doOutput", "1") != "0",
            "priority": data.get("priority", ""),
            "interval": data.get("interval", ""),
            "color": color,
            "text_color": _text_color_for(color),
        })

    # Build layer map: index → name + color
    layer_map: dict[int, dict] = {}
    for cs in root.findall("CutSetting"):
        data = {c.tag: c.attrib.get("Value", "") for c in cs}
        try:
            i = int(data.get("index", "0"))
        except ValueError:
            i = 0
        color = _layer_color(i)
        layer_map[i] = {
            "name": data.get("name", f"C{i:02d}"),
            "color": color,
            "text_color": _text_color_for(color),
        }

    shape_counts: dict[str, int] = {}
    shape_layer_counts: dict[int, int] = {}
    text_strings: list[str] = []
    for s in root.iter("Shape"):
        t = s.attrib.get("Type", "Unknown")
        shape_counts[t] = shape_counts.get(t, 0) + 1
        try:
            cut_idx = int(s.attrib.get("CutIndex", "0"))
        except ValueError:
            cut_idx = 0
        shape_layer_counts[cut_idx] = shape_layer_counts.get(cut_idx, 0) + 1
        if t == "Text":
            txt = s.attrib.get("Str", "").strip()
            if txt and txt not in text_strings:
                text_strings.append(txt)

    shapes_by_layer = []
    for idx in sorted(shape_layer_counts):
        info = layer_map.get(idx, {
            "name": f"C{idx:02d}",
            "color": _layer_color(idx),
            "text_color": _text_color_for(_layer_color(idx)),
        })
        shapes_by_layer.append({
            "layer_index": idx,
            "layer_name": info["name"],
            "color": info["color"],
            "text_color": info["text_color"],
            "count": shape_layer_counts[idx],
        })

    # --- Time estimate (improved: vector/raster, corners, short-segment penalties) ---
    job_estimates = _lb_estimate_job(root)
    total_seconds = sum(
        e.vector.time_seconds + e.raster.time_seconds
        for e in job_estimates.values()
    )
    time_by_layer = []
    for ci in sorted(job_estimates):
        est = job_estimates[ci]
        lc = layer_map.get(ci, {})
        layer_total = est.vector.time_seconds + est.raster.time_seconds
        time_by_layer.append({
            "cut_index": ci,
            "name": est.name,
            "layer_type": est.layer_type,
            "passes": est.num_passes,
            "speed_mm_s": est.speed,
            "do_output": est.do_output,
            "color": lc.get("color", _layer_color(ci)),
            "text_color": lc.get("text_color", "#222222"),
            "has_vector": est.vector.num_paths > 0,
            "vector_paths": est.vector.num_paths,
            "vector_length_mm": round(est.vector.cut_length_mm, 2),
            "vector_corners": est.vector.num_corners,
            "vector_time": _fmt_time(est.vector.time_seconds) if est.vector.time_seconds else "",
            "has_raster": est.raster.num_objects > 0,
            "raster_objects": est.raster.num_objects,
            "raster_lines": est.raster.scan_lines,
            "raster_time": _fmt_time(est.raster.time_seconds) if est.raster.time_seconds else "",
            "layer_time": _fmt_time(layer_total),
            "layer_seconds": layer_total,
        })

    time_estimate = {
        "total_time": _fmt_time(total_seconds) if total_seconds else None,
        "total_seconds": total_seconds,
        "by_layer": time_by_layer,
    }

    return {
        "app_version": app_version,
        "device_name": device_name,
        "material_height": material_height,
        "mirror_x": mirror_x,
        "mirror_y": mirror_y,
        "format_version": format_version,
        "notes": notes,
        "layers": layers,
        "shape_counts": shape_counts,
        "shapes_by_layer": shapes_by_layer,
        "text_strings": text_strings[:20],
        "time_estimate": time_estimate,
    }


class LightBurnPlugin:
    name = "lightburn"

    def can_handle(self, path: Path) -> bool:
        return is_likely_lightburn_project(path)

    def index(self, path: Path) -> IndexRecord:
        thumb_root = getattr(self, "thumb_root", None)
        scan_root_attr = getattr(self, "scan_root", None)
        info = extract_notes_and_thumbnail(path, thumb_root=thumb_root, scan_root=scan_root_attr)
        return IndexRecord(
            path=info.path,
            directory=path.parent,
            notes=info.notes,
            thumbnail_path=info.thumbnail_path,
            error=info.error,
        )
