#!/usr/bin/env python3
"""
Extract useful information from an SVG file.

Usage:
    python svg_extract.py input.svg
    python svg_extract.py input.svg --json
"""

from __future__ import annotations

import argparse
import json
import math
import pdb
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def parse_points(points_text: str) -> list[tuple[float, float]]:
    nums = re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", points_text or "")
    values = [float(n) for n in nums]
    pts: list[tuple[float, float]] = []
    for i in range(0, len(values) - 1, 2):
        pts.append((values[i], values[i + 1]))
    return pts


def cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    mt = 1.0 - t
    x = (
        (mt ** 3) * p0[0]
        + 3 * (mt ** 2) * t * p1[0]
        + 3 * mt * (t ** 2) * p2[0]
        + (t ** 3) * p3[0]
    )
    y = (
        (mt ** 3) * p0[1]
        + 3 * (mt ** 2) * t * p1[1]
        + 3 * mt * (t ** 2) * p2[1]
        + (t ** 3) * p3[1]
    )
    return x, y


def quadratic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    mt = 1.0 - t
    x = (mt ** 2) * p0[0] + 2 * mt * t * p1[0] + (t ** 2) * p2[0]
    y = (mt ** 2) * p0[1] + 2 * mt * t * p1[1] + (t ** 2) * p2[1]
    return x, y


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def arc_to_points(
    x1: float,
    y1: float,
    rx: float,
    ry: float,
    phi_deg: float,
    large_arc: int,
    sweep: int,
    x2: float,
    y2: float,
    steps: int = 24,
) -> list[tuple[float, float]]:
    # SVG arc implementation based on the SVG spec.
    if rx == 0 or ry == 0:
        return [(x1, y1), (x2, y2)]

    phi = math.radians(phi_deg % 360.0)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx2 = (x1 - x2) / 2.0
    dy2 = (y1 - y2) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    rx = abs(rx)
    ry = abs(ry)

    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    sign = -1 if large_arc == sweep else 1
    numerator = (rx ** 2) * (ry ** 2) - (rx ** 2) * (y1p ** 2) - (ry ** 2) * (x1p ** 2)
    denom = (rx ** 2) * (y1p ** 2) + (ry ** 2) * (x1p ** 2)
    factor = 0.0 if denom == 0 else sign * math.sqrt(max(0.0, numerator / denom))
    cxp = factor * ((rx * y1p) / ry)
    cyp = factor * (-(ry * x1p) / rx)

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def angle(u: tuple[float, float], v: tuple[float, float]) -> float:
        dot = u[0] * v[0] + u[1] * v[1]
        det = u[0] * v[1] - u[1] * v[0]
        return math.atan2(det, dot)

    v1 = ((x1p - cxp) / rx, (y1p - cyp) / ry)
    v2 = ((-x1p - cxp) / rx, (-y1p - cyp) / ry)

    theta1 = angle((1.0, 0.0), v1)
    delta_theta = angle(v1, v2)

    if not sweep and delta_theta > 0:
        delta_theta -= 2 * math.pi
    elif sweep and delta_theta < 0:
        delta_theta += 2 * math.pi

    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = theta1 + delta_theta * (i / steps)
        ct = math.cos(t)
        st = math.sin(t)
        x = cx + rx * ct * cos_phi - ry * st * sin_phi
        y = cy + rx * ct * sin_phi + ry * st * cos_phi
        pts.append((x, y))
    return pts


def tokenize_path(d: str) -> list[str]:
    return re.findall(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d or "")


def path_metrics(d: str) -> dict[str, Any]:
    tokens = tokenize_path(d)
    i = 0
    cmd = ""
    x = y = 0.0
    start_x = start_y = 0.0
    last_ctrl: tuple[float, float] | None = None
    points: list[tuple[float, float]] = []
    length = 0.0
    closed = False

    def has_num(idx: int) -> bool:
        return idx < len(tokens) and re.match(r"[-+.]|\d", tokens[idx]) is not None

    def add_point(px: float, py: float) -> None:
        points.append((px, py))

    while i < len(tokens):
        token = tokens[i]
        if re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", token):
            cmd = token
            i += 1
        if not cmd:
            raise ValueError("Path data starts without a command.")

        if cmd in ("M", "m"):
            first = True
            while i + 1 < len(tokens) and has_num(i):
                nx = float(tokens[i])
                ny = float(tokens[i + 1])
                i += 2
                if cmd == "m":
                    nx += x
                    ny += y
                x, y = nx, ny
                if first:
                    start_x, start_y = x, y
                    add_point(x, y)
                    first = False
                else:
                    length += dist(points[-1], (x, y))
                    add_point(x, y)
            last_ctrl = None
            cmd = "L" if cmd == "M" else "l"

        elif cmd in ("L", "l"):
            while i + 1 < len(tokens) and has_num(i):
                nx = float(tokens[i])
                ny = float(tokens[i + 1])
                i += 2
                if cmd == "l":
                    nx += x
                    ny += y
                length += dist((x, y), (nx, ny))
                x, y = nx, ny
                add_point(x, y)
            last_ctrl = None

        elif cmd in ("H", "h"):
            while i < len(tokens) and has_num(i):
                nx = float(tokens[i])
                i += 1
                if cmd == "h":
                    nx += x
                length += dist((x, y), (nx, y))
                x = nx
                add_point(x, y)
            last_ctrl = None

        elif cmd in ("V", "v"):
            while i < len(tokens) and has_num(i):
                ny = float(tokens[i])
                i += 1
                if cmd == "v":
                    ny += y
                length += dist((x, y), (x, ny))
                y = ny
                add_point(x, y)
            last_ctrl = None

        elif cmd in ("C", "c"):
            while i + 5 < len(tokens) and has_num(i):
                x1 = float(tokens[i])
                y1 = float(tokens[i + 1])
                x2 = float(tokens[i + 2])
                y2 = float(tokens[i + 3])
                x3 = float(tokens[i + 4])
                y3 = float(tokens[i + 5])
                i += 6
                if cmd == "c":
                    x1 += x
                    y1 += y
                    x2 += x
                    y2 += y
                    x3 += x
                    y3 += y
                prev = (x, y)
                samples = [cubic_bezier(prev, (x1, y1), (x2, y2), (x3, y3), t / 20.0) for t in range(1, 21)]
                for pt in samples:
                    length += dist(prev, pt)
                    prev = pt
                    add_point(*pt)
                x, y = x3, y3
                last_ctrl = (x2, y2)

        elif cmd in ("S", "s"):
            while i + 3 < len(tokens) and has_num(i):
                if last_ctrl is None:
                    x1, y1 = x, y
                else:
                    x1 = 2 * x - last_ctrl[0]
                    y1 = 2 * y - last_ctrl[1]
                x2 = float(tokens[i])
                y2 = float(tokens[i + 1])
                x3 = float(tokens[i + 2])
                y3 = float(tokens[i + 3])
                i += 4
                if cmd == "s":
                    x2 += x
                    y2 += y
                    x3 += x
                    y3 += y
                prev = (x, y)
                samples = [cubic_bezier(prev, (x1, y1), (x2, y2), (x3, y3), t / 20.0) for t in range(1, 21)]
                for pt in samples:
                    length += dist(prev, pt)
                    prev = pt
                    add_point(*pt)
                x, y = x3, y3
                last_ctrl = (x2, y2)

        elif cmd in ("Q", "q"):
            while i + 3 < len(tokens) and has_num(i):
                x1 = float(tokens[i])
                y1 = float(tokens[i + 1])
                x2 = float(tokens[i + 2])
                y2 = float(tokens[i + 3])
                i += 4
                if cmd == "q":
                    x1 += x
                    y1 += y
                    x2 += x
                    y2 += y
                prev = (x, y)
                samples = [quadratic_bezier(prev, (x1, y1), (x2, y2), t / 20.0) for t in range(1, 21)]
                for pt in samples:
                    length += dist(prev, pt)
                    prev = pt
                    add_point(*pt)
                x, y = x2, y2
                last_ctrl = (x1, y1)

        elif cmd in ("T", "t"):
            while i + 1 < len(tokens) and has_num(i):
                if last_ctrl is None:
                    x1, y1 = x, y
                else:
                    x1 = 2 * x - last_ctrl[0]
                    y1 = 2 * y - last_ctrl[1]
                x2 = float(tokens[i])
                y2 = float(tokens[i + 1])
                i += 2
                if cmd == "t":
                    x2 += x
                    y2 += y
                prev = (x, y)
                samples = [quadratic_bezier(prev, (x1, y1), (x2, y2), t / 20.0) for t in range(1, 21)]
                for pt in samples:
                    length += dist(prev, pt)
                    prev = pt
                    add_point(*pt)
                x, y = x2, y2
                last_ctrl = (x1, y1)

        elif cmd in ("A", "a"):
            while i + 6 < len(tokens) and has_num(i):
                rx = float(tokens[i])
                ry = float(tokens[i + 1])
                phi = float(tokens[i + 2])
                large_arc = int(float(tokens[i + 3]))
                sweep = int(float(tokens[i + 4]))
                x2 = float(tokens[i + 5])
                y2 = float(tokens[i + 6])
                i += 7
                if cmd == "a":
                    x2 += x
                    y2 += y
                arc_pts = arc_to_points(x, y, rx, ry, phi, large_arc, sweep, x2, y2)
                prev = (x, y)
                for pt in arc_pts[1:]:
                    length += dist(prev, pt)
                    prev = pt
                    add_point(*pt)
                x, y = x2, y2
                last_ctrl = None

        elif cmd in ("Z", "z"):
            length += dist((x, y), (start_x, start_y))
            x, y = start_x, start_y
            add_point(x, y)
            closed = True
            last_ctrl = None
            # advance only if we didn't already consume this command
        else:
            raise ValueError(f"Unsupported path command: {cmd}")

    xs = [p[0] for p in points] if points else []
    ys = [p[1] for p in points] if points else []
    return {
        "length": length,
        "closed": closed,
        "point_count": len(points),
        "bounds": {
            "min_x": min(xs) if xs else None,
            "min_y": min(ys) if ys else None,
            "max_x": max(xs) if xs else None,
            "max_y": max(ys) if ys else None,
        },
    }


def update_bounds(bounds: dict[str, float | None], x: float, y: float) -> None:
    if bounds["min_x"] is None or x < bounds["min_x"]:
        bounds["min_x"] = x
    if bounds["max_x"] is None or x > bounds["max_x"]:
        bounds["max_x"] = x
    if bounds["min_y"] is None or y < bounds["min_y"]:
        bounds["min_y"] = y
    if bounds["max_y"] is None or y > bounds["max_y"]:
        bounds["max_y"] = y


def extract_svg(path: Path) -> dict[str, Any]:
    tree = ET.parse(path)
    root = tree.getroot()

    info: dict[str, Any] = {
        "file": str(path),
        "file_size": path.stat().st_size,
        "root_tag": strip_ns(root.tag),
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "viewBox": root.attrib.get("viewBox"),
        "namespaces": sorted({tag.split("}")[0][1:] for tag in [el.tag for el in root.iter()] if tag.startswith("{")}),
        "counts": Counter(),
        "texts": [],
        "groups": [],
        "paths": [],
        "styles": [],
        "overall_bounds": {"min_x": None, "min_y": None, "max_x": None, "max_y": None},
        "estimated_total_path_length": 0.0,
        "closed_paths": 0,
        "open_paths": 0,
    }

    for el in root.iter():
        tag = strip_ns(el.tag)
        info["counts"][tag] += 1

        if tag == "g":
            group_id = el.attrib.get("id")
            label = el.attrib.get("{http://www.inkscape.org/namespaces/inkscape}label")
            if group_id or label:
                info["groups"].append({"id": group_id, "label": label})

        if tag == "style" and el.text:
            info["styles"].append(el.text.strip())

        if tag == "text":
            text_content = "".join(el.itertext()).strip()
            if text_content:
                info["texts"].append(
                    {
                        "text": text_content,
                        "x": el.attrib.get("x"),
                        "y": el.attrib.get("y"),
                        "id": el.attrib.get("id"),
                    }
                )

        if tag == "path":
            d = el.attrib.get("d", "")
            metrics = path_metrics(d)
            info["paths"].append(
                {
                    "id": el.attrib.get("id"),
                    "style": el.attrib.get("style"),
                    "stroke": el.attrib.get("stroke"),
                    "fill": el.attrib.get("fill"),
                    "length": metrics["length"],
                    "closed": metrics["closed"],
                    "bounds": metrics["bounds"],
                    "d_preview": d[:140],
                }
            )
            info["estimated_total_path_length"] += metrics["length"]
            if metrics["closed"]:
                info["closed_paths"] += 1
            else:
                info["open_paths"] += 1
            b = metrics["bounds"]
            if b["min_x"] is not None:
                update_bounds(info["overall_bounds"], b["min_x"], b["min_y"])
                update_bounds(info["overall_bounds"], b["max_x"], b["max_y"])

        elif tag == "line":
            x1 = parse_number(el.attrib.get("x1")) or 0.0
            y1 = parse_number(el.attrib.get("y1")) or 0.0
            x2 = parse_number(el.attrib.get("x2")) or 0.0
            y2 = parse_number(el.attrib.get("y2")) or 0.0
            update_bounds(info["overall_bounds"], x1, y1)
            update_bounds(info["overall_bounds"], x2, y2)

        elif tag in {"polyline", "polygon"}:
            pts = parse_points(el.attrib.get("points", ""))
            for px, py in pts:
                update_bounds(info["overall_bounds"], px, py)

        elif tag == "rect":
            x = parse_number(el.attrib.get("x")) or 0.0
            y = parse_number(el.attrib.get("y")) or 0.0
            width = parse_number(el.attrib.get("width")) or 0.0
            height = parse_number(el.attrib.get("height")) or 0.0
            update_bounds(info["overall_bounds"], x, y)
            update_bounds(info["overall_bounds"], x + width, y + height)

        elif tag == "circle":
            cx = parse_number(el.attrib.get("cx")) or 0.0
            cy = parse_number(el.attrib.get("cy")) or 0.0
            r = parse_number(el.attrib.get("r")) or 0.0
            update_bounds(info["overall_bounds"], cx - r, cy - r)
            update_bounds(info["overall_bounds"], cx + r, cy + r)

        elif tag == "ellipse":
            cx = parse_number(el.attrib.get("cx")) or 0.0
            cy = parse_number(el.attrib.get("cy")) or 0.0
            rx = parse_number(el.attrib.get("rx")) or 0.0
            ry = parse_number(el.attrib.get("ry")) or 0.0
            update_bounds(info["overall_bounds"], cx - rx, cy - ry)
            update_bounds(info["overall_bounds"], cx + rx, cy + ry)

    counts = dict(info["counts"])
    info["counts"] = counts

    if root.attrib.get("viewBox"):
        parts = root.attrib["viewBox"].replace(",", " ").split()
        if len(parts) == 4:
            try:
                vx, vy, vw, vh = [float(p) for p in parts]
                info["viewBox_parsed"] = {"min_x": vx, "min_y": vy, "width": vw, "height": vh}
            except ValueError:
                info["viewBox_parsed"] = None
        else:
            info["viewBox_parsed"] = None
    else:
        info["viewBox_parsed"] = None

    min_x = info["overall_bounds"]["min_x"]
    min_y = info["overall_bounds"]["min_y"]
    max_x = info["overall_bounds"]["max_x"]
    max_y = info["overall_bounds"]["max_y"]
    if None not in (min_x, min_y, max_x, max_y):
        info["overall_size"] = {"width": max_x - min_x, "height": max_y - min_y}
    else:
        info["overall_size"] = None

    unique_texts = sorted({item["text"] for item in info["texts"]})
    info["unique_texts"] = unique_texts

    return info


def format_report(info: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("SVG Summary")
    lines.append("===========")
    lines.append(f"File: {info['file']}")
    lines.append(f"File size: {info['file_size']:,} bytes")
    lines.append("")
    lines.append("Root")
    lines.append("----")
    lines.append(f"Tag: {info['root_tag']}")
    lines.append(f"Width: {info['width']}")
    lines.append(f"Height: {info['height']}")
    lines.append(f"viewBox: {info['viewBox']}")
    lines.append(f"Namespaces: {', '.join(info['namespaces']) if info['namespaces'] else 'None'}")
    lines.append("")
    lines.append("Element counts")
    lines.append("--------------")
    for key in sorted(info["counts"]):
        lines.append(f"{key}: {info['counts'][key]}")
    lines.append("")
    lines.append("Groups / layers")
    lines.append("---------------")
    if info["groups"]:
        for group in info["groups"]:
            lines.append(f"id={group['id']!r}, label={group['label']!r}")
    else:
        lines.append("None")
    lines.append("")
    lines.append("Text")
    lines.append("----")
    if info["texts"]:
        for item in info["texts"]:
            lines.append(f"{item['text']!r} (x={item['x']}, y={item['y']}, id={item['id']})")
    else:
        lines.append("No text elements found")
    lines.append("")
    lines.append("Geometry")
    lines.append("--------")
    ob = info["overall_bounds"]
    lines.append(f"Overall bounds: min=({ob['min_x']}, {ob['min_y']}), max=({ob['max_x']}, {ob['max_y']})")
    lines.append(f"Overall size: {info['overall_size']}")
    lines.append(f"Estimated total path length: {info['estimated_total_path_length']:.3f}")
    lines.append(f"Closed paths: {info['closed_paths']}")
    lines.append(f"Open paths: {info['open_paths']}")
    lines.append("")
    lines.append("Path details")
    lines.append("------------")
    for idx, path in enumerate(info["paths"][:20], start=1):
        lines.append(
            f"{idx}. id={path['id']!r}, closed={path['closed']}, length={path['length']:.3f}, "
            f"bounds={path['bounds']}, d={path['d_preview']!r}"
        )
    if len(info["paths"]) > 20:
        lines.append(f"... {len(info['paths']) - 20} more paths omitted")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract useful information from an SVG file.")
    parser.add_argument("filename", help="Path to the SVG file")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    svg_path = Path(args.filename)
    if not svg_path.exists():
        print(f"Error: file not found: {svg_path}", file=sys.stderr)
        sys.exit(1)

    info = extract_svg(svg_path)

    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        print(format_report(info))


if __name__ == "__main__":
    main()
    pdb.set_trace()
