from __future__ import annotations

import base64
import binascii
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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

def extract_notes_and_thumbnail(path: Path) -> IndexRecord:
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
            expected = thumbnail_path_for(path)
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

    # --- Time estimate ---
    OVERHEAD = 1.15
    layer_lengths: dict[int, float] = {}
    layer_path_counts: dict[int, int] = {}
    for el in root.iter():
        if el.tag == "Shape" and el.attrib.get("Type") == "Path":
            ci = el.attrib.get("CutIndex")
            if ci is not None:
                ci = int(ci)
                layer_lengths[ci] = layer_lengths.get(ci, 0.0) + _shape_path_length(el)
                layer_path_counts[ci] = layer_path_counts.get(ci, 0) + 1
        elif el.tag == "BackupPath" and el.attrib.get("Type") == "Path":
            ci = el.attrib.get("CutIndex")
            if ci is not None:
                ci = int(ci)
                layer_lengths[ci] = layer_lengths.get(ci, 0.0) + _shape_path_length(el)
                layer_path_counts[ci] = layer_path_counts.get(ci, 0) + 1

    # Build a fast lookup from layer list
    layer_settings: dict[int, dict] = {int(l["index"]): l for l in layers if l["index"] != "?"}

    total_active_mm = 0.0
    total_raw_s = 0.0
    total_overhead_s = 0.0
    time_by_layer = []
    for ci in sorted(layer_lengths):
        lsetting = layer_settings.get(ci, {})
        length_mm = layer_lengths[ci]
        passes = int(lsetting.get("passes") or 1)
        do_output = lsetting.get("do_output", True)
        speed = float(lsetting.get("speed") or 0)
        active_mm = length_mm * passes if do_output else 0.0
        raw_s = (active_mm / speed) if (do_output and speed > 0) else None
        overhead_s = (raw_s * OVERHEAD) if raw_s is not None else None
        if raw_s is not None:
            total_active_mm += active_mm
            total_raw_s += raw_s
            total_overhead_s += overhead_s
        time_by_layer.append({
            "cut_index": ci,
            "name": lsetting.get("name", f"C{ci:02d}"),
            "path_count": layer_path_counts.get(ci, 0),
            "length_mm": round(length_mm, 2),
            "active_length_mm": round(active_mm, 2),
            "passes": passes,
            "speed_mm_s": speed,
            "do_output": do_output,
            "time_raw": _fmt_time(raw_s),
            "time_overhead": _fmt_time(overhead_s),
            "color": layer_map.get(ci, {}).get("color", _layer_color(ci)),
            "text_color": layer_map.get(ci, {}).get("text_color", "#222222"),
        })

    time_estimate = {
        "total_active_length_mm": round(total_active_mm, 2),
        "time_raw": _fmt_time(total_raw_s if total_raw_s else None),
        "time_overhead": _fmt_time(total_overhead_s if total_overhead_s else None),
        "overhead_factor": OVERHEAD,
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
        info = extract_notes_and_thumbnail(path )
        return IndexRecord(
            path=info.path,
            directory=path.parent,
            notes=info.notes,
            thumbnail_path=info.thumbnail_path,
            error=info.error,
        )
