from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from maker_file_index.model import IndexRecord


# ---------------------------------------------------------------------------
# SVG detail extraction (ported from scripts/svg_extract.py)
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", value)
    return float(m.group(0)) if m else None


def _parse_points(text: str) -> list[tuple[float, float]]:
    nums = re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", text or "")
    vals = [float(n) for n in nums]
    return [(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]


def _cubic_bezier(p0, p1, p2, p3, t):
    mt = 1.0 - t
    return (
        mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
        mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1],
    )


def _quad_bezier(p0, p1, p2, t):
    mt = 1.0 - t
    return (mt**2*p0[0] + 2*mt*t*p1[0] + t**2*p2[0],
            mt**2*p0[1] + 2*mt*t*p1[1] + t**2*p2[1])


def _path_length(d: str) -> tuple[float, bool]:
    """Return (total_length, is_closed) for an SVG path d attribute."""
    tokens = re.findall(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d or "")
    i = 0
    cmd = ""
    x = y = sx = sy = 0.0
    last_ctrl = None
    length = 0.0
    closed = False
    prev = (x, y)

    def has_num(idx):
        return idx < len(tokens) and bool(re.match(r"[-+.]|\d", tokens[idx]))

    while i < len(tokens):
        tok = tokens[i]
        if re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tok):
            cmd = tok; i += 1
        if not cmd:
            break

        if cmd in "Mm":
            while i + 1 < len(tokens) and has_num(i):
                nx, ny = float(tokens[i]), float(tokens[i+1]); i += 2
                if cmd == "m": nx += x; ny += y
                if cmd == "M" and x == 0 and y == 0:
                    sx, sy = nx, ny
                elif cmd == "m" and length == 0:
                    sx, sy = nx, ny
                else:
                    length += math.hypot(nx - x, ny - y)
                x, y = nx, ny; sx, sy = (sx, sy) if length == 0 else (sx, sy)
                prev = (x, y)
                last_ctrl = None
            cmd = "L" if cmd == "M" else "l"

        elif cmd in "Ll":
            while i + 1 < len(tokens) and has_num(i):
                nx, ny = float(tokens[i]), float(tokens[i+1]); i += 2
                if cmd == "l": nx += x; ny += y
                length += math.hypot(nx - x, ny - y); x, y = nx, ny; prev = (x, y); last_ctrl = None

        elif cmd in "Hh":
            while i < len(tokens) and has_num(i):
                nx = float(tokens[i]); i += 1
                if cmd == "h": nx += x
                length += abs(nx - x); x = nx; prev = (x, y); last_ctrl = None

        elif cmd in "Vv":
            while i < len(tokens) and has_num(i):
                ny = float(tokens[i]); i += 1
                if cmd == "v": ny += y
                length += abs(ny - y); y = ny; prev = (x, y); last_ctrl = None

        elif cmd in "Cc":
            while i + 5 < len(tokens) and has_num(i):
                x1,y1,x2,y2,x3,y3 = [float(tokens[i+k]) for k in range(6)]; i += 6
                if cmd == "c": x1+=x;y1+=y;x2+=x;y2+=y;x3+=x;y3+=y
                p = (x,y)
                for t in [k/20 for k in range(1,21)]:
                    q = _cubic_bezier(p,(x1,y1),(x2,y2),(x3,y3),t)
                    length += math.hypot(q[0]-p[0],q[1]-p[1]); p = q
                x,y,last_ctrl = x3,y3,(x2,y2); prev=(x,y)

        elif cmd in "Ss":
            while i + 3 < len(tokens) and has_num(i):
                x1 = 2*x - last_ctrl[0] if last_ctrl else x
                y1 = 2*y - last_ctrl[1] if last_ctrl else y
                x2,y2,x3,y3 = [float(tokens[i+k]) for k in range(4)]; i += 4
                if cmd == "s": x2+=x;y2+=y;x3+=x;y3+=y
                p = (x,y)
                for t in [k/20 for k in range(1,21)]:
                    q = _cubic_bezier(p,(x1,y1),(x2,y2),(x3,y3),t)
                    length += math.hypot(q[0]-p[0],q[1]-p[1]); p = q
                x,y,last_ctrl = x3,y3,(x2,y2); prev=(x,y)

        elif cmd in "Qq":
            while i + 3 < len(tokens) and has_num(i):
                x1,y1,x2,y2 = [float(tokens[i+k]) for k in range(4)]; i += 4
                if cmd == "q": x1+=x;y1+=y;x2+=x;y2+=y
                p = (x,y)
                for t in [k/20 for k in range(1,21)]:
                    q = _quad_bezier(p,(x1,y1),(x2,y2),t)
                    length += math.hypot(q[0]-p[0],q[1]-p[1]); p = q
                x,y,last_ctrl = x2,y2,(x1,y1); prev=(x,y)

        elif cmd in "Tt":
            while i + 1 < len(tokens) and has_num(i):
                x1 = 2*x - last_ctrl[0] if last_ctrl else x
                y1 = 2*y - last_ctrl[1] if last_ctrl else y
                x2,y2 = float(tokens[i]),float(tokens[i+1]); i += 2
                if cmd == "t": x2+=x;y2+=y
                p = (x,y)
                for t in [k/20 for k in range(1,21)]:
                    q = _quad_bezier(p,(x1,y1),(x2,y2),t)
                    length += math.hypot(q[0]-p[0],q[1]-p[1]); p = q
                x,y,last_ctrl = x2,y2,(x1,y1); prev=(x,y)

        elif cmd in "Aa":
            while i + 6 < len(tokens) and has_num(i):
                rx,ry,phi = float(tokens[i]),float(tokens[i+1]),float(tokens[i+2])
                large_arc,sweep = int(float(tokens[i+3])),int(float(tokens[i+4]))
                x2,y2 = float(tokens[i+5]),float(tokens[i+6]); i += 7
                if cmd == "a": x2+=x;y2+=y
                # approximate arc as straight line (good enough for length estimate)
                length += math.hypot(x2-x,y2-y)
                x,y = x2,y2; prev=(x,y); last_ctrl=None

        elif cmd in "Zz":
            length += math.hypot(sx-x, sy-y); x,y = sx,sy; closed=True; last_ctrl=None

        else:
            break

    return length, closed


def _detect_unit(value: str | None) -> str:
    """Return the unit suffix from an SVG dimension attribute, or 'px'."""
    if not value:
        return "px"
    m = re.search(r"(mm|cm|in|pt|pc|px|em|rem|%)\s*$", value.strip())
    return m.group(1) if m else "px"


def extract_svg_details(path: Path) -> dict:
    """Extract metadata and geometry from an SVG file."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        width_raw = root.attrib.get("width", "")
        height_raw = root.attrib.get("height", "")
        viewbox_raw = root.attrib.get("viewBox", "")
        unit = _detect_unit(width_raw) or _detect_unit(height_raw)

        # Parse viewBox
        viewbox_parsed = None
        doc_width = doc_height = None
        if viewbox_raw:
            parts = viewbox_raw.replace(",", " ").split()
            if len(parts) == 4:
                try:
                    vx, vy, vw, vh = [float(p) for p in parts]
                    viewbox_parsed = {"x": vx, "y": vy, "w": vw, "h": vh}
                    doc_width = vw
                    doc_height = vh
                except ValueError:
                    pass
        if doc_width is None:
            doc_width = _parse_number(width_raw)
        if doc_height is None:
            doc_height = _parse_number(height_raw)

        # Count elements by tag
        counts: Counter[str] = Counter()
        groups: list[dict] = []
        texts: list[str] = []
        path_count = 0
        closed_paths = 0
        open_paths = 0
        total_path_length = 0.0
        namespaces: set[str] = set()

        INTERESTING_TAGS = {"path","rect","circle","ellipse","line","polyline","polygon",
                            "text","tspan","g","use","image","symbol","defs","clipPath","mask"}

        for el in root.iter():
            tag = _strip_ns(el.tag)
            if el.tag.startswith("{"):
                ns = el.tag.split("}")[0][1:]
                namespaces.add(ns)
            if tag in INTERESTING_TAGS:
                counts[tag] += 1

            if tag == "g":
                gid = el.attrib.get("id", "")
                label = el.attrib.get("{http://www.inkscape.org/namespaces/inkscape}label", "")
                if gid or label:
                    groups.append({"id": gid, "label": label})

            if tag == "text":
                content = "".join(el.itertext()).strip()
                if content and content not in texts:
                    texts.append(content)

            if tag == "path":
                d = el.attrib.get("d", "")
                try:
                    plen, is_closed = _path_length(d)
                    total_path_length += plen
                    path_count += 1
                    if is_closed:
                        closed_paths += 1
                    else:
                        open_paths += 1
                except Exception:
                    path_count += 1
                    open_paths += 1

        # Detect authoring tool from namespaces
        tool = ""
        ns_str = " ".join(namespaces)
        if "inkscape" in ns_str:
            tool = "Inkscape"
        elif "illustrator" in ns_str or "adobe" in ns_str:
            tool = "Adobe Illustrator"
        elif "corel" in ns_str:
            tool = "CorelDRAW"
        elif "sketch" in ns_str:
            tool = "Sketch"

        return {
            "width": width_raw,
            "height": height_raw,
            "viewbox": viewbox_raw,
            "unit": unit,
            "doc_width": f"{doc_width:.2f}" if doc_width is not None else "",
            "doc_height": f"{doc_height:.2f}" if doc_height is not None else "",
            "tool": tool,
            "counts": dict(counts.most_common()),
            "path_count": path_count,
            "closed_paths": closed_paths,
            "open_paths": open_paths,
            "total_path_length": f"{total_path_length:.2f}",
            "groups": groups[:50],
            "texts": texts[:30],
            "error": "",
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


class SVGPlugin:
    name = "svg"
    extensions = {".svg"}

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def index(self, path: Path) -> IndexRecord:
        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=path,
            error="",
        )
