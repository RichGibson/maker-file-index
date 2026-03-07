#!/usr/bin/env python3
"""
Extract useful information from a DXF file.

Usage:
    python dxf_extract_v2.py input.dxf
    python dxf_extract_v2.py input.dxf --json
"""

from __future__ import annotations

import argparse
import json
import math
import pdb
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PAIR_RE = re.compile(r"^\s*(-?\d+)\s*$")


def parse_ascii_dxf_pairs(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    pairs: list[tuple[int, str]] = []
    i = 0
    while i + 1 < len(lines):
        code_line = lines[i]
        value_line = lines[i + 1]
        i += 2
        match = PAIR_RE.match(code_line)
        if not match:
            continue
        code = int(match.group(1))
        pairs.append((code, value_line.rstrip("\n\r")))
    return pairs


def as_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except Exception:
        return None


def as_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except Exception:
        return None


def distance(p1: tuple[float, float, float], p2: tuple[float, float, float]) -> float:
    return math.sqrt(
        (p2[0] - p1[0]) ** 2 +
        (p2[1] - p1[1]) ** 2 +
        (p2[2] - p1[2]) ** 2
    )


def update_bounds(bounds: dict[str, float | None], x: float, y: float, z: float = 0.0) -> None:
    if bounds["min_x"] is None or x < bounds["min_x"]:
        bounds["min_x"] = x
    if bounds["max_x"] is None or x > bounds["max_x"]:
        bounds["max_x"] = x
    if bounds["min_y"] is None or y < bounds["min_y"]:
        bounds["min_y"] = y
    if bounds["max_y"] is None or y > bounds["max_y"]:
        bounds["max_y"] = y
    if bounds["min_z"] is None or z < bounds["min_z"]:
        bounds["min_z"] = z
    if bounds["max_z"] is None or z > bounds["max_z"]:
        bounds["max_z"] = z


def empty_bounds() -> dict[str, float | None]:
    return {
        "min_x": None,
        "min_y": None,
        "min_z": None,
        "max_x": None,
        "max_y": None,
        "max_z": None,
    }


def bounds_with_sizes(bounds: dict[str, float | None]) -> dict[str, float | None]:
    result = dict(bounds)
    if None not in (bounds["min_x"], bounds["max_x"]):
        result["size_x"] = bounds["max_x"] - bounds["min_x"]
    else:
        result["size_x"] = None
    if None not in (bounds["min_y"], bounds["max_y"]):
        result["size_y"] = bounds["max_y"] - bounds["min_y"]
    else:
        result["size_y"] = None
    if None not in (bounds["min_z"], bounds["max_z"]):
        result["size_z"] = bounds["max_z"] - bounds["min_z"]
    else:
        result["size_z"] = None
    return result


def entity_length(entity_type: str, data: dict[int, list[str]]) -> float | None:
    entity_type = entity_type.upper()

    if entity_type == "LINE":
        x1 = as_float(data.get(10, ["0"])[0]) or 0.0
        y1 = as_float(data.get(20, ["0"])[0]) or 0.0
        z1 = as_float(data.get(30, ["0"])[0]) or 0.0
        x2 = as_float(data.get(11, ["0"])[0]) or 0.0
        y2 = as_float(data.get(21, ["0"])[0]) or 0.0
        z2 = as_float(data.get(31, ["0"])[0]) or 0.0
        return distance((x1, y1, z1), (x2, y2, z2))

    if entity_type in {"LWPOLYLINE", "POLYLINE"}:
        xs = [as_float(v) for v in data.get(10, [])]
        ys = [as_float(v) for v in data.get(20, [])]
        pts = [(x or 0.0, y or 0.0, 0.0) for x, y in zip(xs, ys)]
        if len(pts) < 2:
            return 0.0
        total = sum(distance(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        closed_flag = as_int(data.get(70, ["0"])[0] if data.get(70) else "0") or 0
        if closed_flag & 1:
            total += distance(pts[-1], pts[0])
        return total

    if entity_type == "CIRCLE":
        radius = as_float(data.get(40, ["0"])[0]) or 0.0
        return 2 * math.pi * radius

    if entity_type == "ARC":
        radius = as_float(data.get(40, ["0"])[0]) or 0.0
        start = math.radians(as_float(data.get(50, ["0"])[0]) or 0.0)
        end = math.radians(as_float(data.get(51, ["0"])[0]) or 0.0)
        delta = end - start
        if delta < 0:
            delta += 2 * math.pi
        return radius * delta

    if entity_type == "ELLIPSE":
        cx = as_float(data.get(10, ["0"])[0]) or 0.0
        cy = as_float(data.get(20, ["0"])[0]) or 0.0
        mx = as_float(data.get(11, ["0"])[0]) or 0.0
        my = as_float(data.get(21, ["0"])[0]) or 0.0
        ratio = as_float(data.get(40, ["1"])[0]) or 1.0
        a = math.hypot(mx, my)
        b = a * ratio
        if a == 0 or b == 0:
            return 0.0
        # Ramanujan approximation, full ellipse; for partial ellipse scale by parameter span.
        full = math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))
        start = as_float(data.get(41, ["0"])[0]) or 0.0
        end = as_float(data.get(42, [str(2 * math.pi)])[0]) or (2 * math.pi)
        span = end - start
        if span < 0:
            span += 2 * math.pi
        return full * (span / (2 * math.pi))

    return None


def collect_entity_bounds(entity_type: str, data: dict[int, list[str]], bounds: dict[str, float | None]) -> None:
    point_code_pairs = [
        (10, 20, 30), (11, 21, 31), (12, 22, 32), (13, 23, 33),
        (14, 24, 34), (15, 25, 35), (16, 26, 36), (17, 27, 37),
    ]
    for xcode, ycode, zcode in point_code_pairs:
        xs = data.get(xcode, [])
        ys = data.get(ycode, [])
        zs = data.get(zcode, [])
        for idx in range(min(len(xs), len(ys))):
            x = as_float(xs[idx])
            y = as_float(ys[idx])
            z = as_float(zs[idx]) if idx < len(zs) else 0.0
            if x is not None and y is not None:
                update_bounds(bounds, x, y, z or 0.0)

    if entity_type.upper() in {"CIRCLE", "ARC"}:
        cx = as_float(data.get(10, ["0"])[0]) or 0.0
        cy = as_float(data.get(20, ["0"])[0]) or 0.0
        cz = as_float(data.get(30, ["0"])[0]) or 0.0
        radius = as_float(data.get(40, ["0"])[0]) or 0.0
        update_bounds(bounds, cx - radius, cy - radius, cz)
        update_bounds(bounds, cx + radius, cy + radius, cz)

    if entity_type.upper() == "ELLIPSE":
        cx = as_float(data.get(10, ["0"])[0]) or 0.0
        cy = as_float(data.get(20, ["0"])[0]) or 0.0
        cz = as_float(data.get(30, ["0"])[0]) or 0.0
        mx = as_float(data.get(11, ["0"])[0]) or 0.0
        my = as_float(data.get(21, ["0"])[0]) or 0.0
        ratio = as_float(data.get(40, ["1"])[0]) or 1.0
        a = math.hypot(mx, my)
        b = a * ratio
        update_bounds(bounds, cx - a, cy - b, cz)
        update_bounds(bounds, cx + a, cy + b, cz)


def parse_dxf(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    is_ascii = b"\x00" not in raw[:1024]

    if not is_ascii:
        raise ValueError("This utility currently supports ASCII DXF files only.")

    text = raw.decode("latin-1", errors="replace")
    pairs = parse_ascii_dxf_pairs(text)

    info: dict[str, Any] = {
        "path": str(path),
        "filename": path.name,
        "file_size_bytes": path.stat().st_size,
        "format": "DXF",
        "dxf_kind": "ascii",
        "header": {},
        "sections_present": [],
        "layers": [],
        "text": {"count": 0, "values": [], "unique_values": []},
        "entity_summary": {
            "total_entities": 0,
            "entity_counts": {},
            "entities_by_layer": {},
            "bounds_from_entities": {},
            "estimated_total_entity_length": 0.0,
            "estimated_length_by_type": {},
            "estimated_length_entity_counts": {},
        },
    }

    current_section: str | None = None
    i = 0
    layers: list[dict[str, Any]] = []
    texts: list[str] = []
    entity_counts: Counter[str] = Counter()
    entities_by_layer: Counter[str] = Counter()
    length_by_type: defaultdict[str, float] = defaultdict(float)
    length_entity_counts: Counter[str] = Counter()
    entity_bounds = empty_bounds()

    while i < len(pairs):
        code, value = pairs[i]

        if code == 0 and value == "SECTION" and i + 1 < len(pairs) and pairs[i + 1][0] == 2:
            current_section = pairs[i + 1][1].strip()
            info["sections_present"].append(current_section)
            i += 2
            continue

        if code == 0 and value == "ENDSEC":
            current_section = None
            i += 1
            continue

        if current_section == "HEADER" and code == 9:
            var_name = value.strip()
            coords: list[float] = []
            j = i + 1
            while j < len(pairs):
                c2, v2 = pairs[j]
                if c2 == 9 or (c2 == 0 and v2 in {"ENDSEC", "SECTION"}):
                    break
                num = as_float(v2)
                if num is not None and c2 in {10, 20, 30, 40, 50, 70}:
                    coords.append(num)
                else:
                    if c2 in {1, 3}:
                        info["header"][var_name] = v2.strip()
                j += 1
            if coords:
                info["header"][var_name] = coords if len(coords) > 1 else coords[0]
            i = j
            continue

        if current_section == "TABLES" and code == 0 and value == "LAYER":
            layer: dict[str, Any] = {}
            j = i + 1
            while j < len(pairs):
                c2, v2 = pairs[j]
                if c2 == 0:
                    break
                if c2 == 2:
                    layer["name"] = v2.strip()
                elif c2 == 62:
                    layer["color"] = as_int(v2)
                elif c2 == 6:
                    layer["linetype"] = v2.strip()
                elif c2 == 70:
                    layer["flags"] = as_int(v2)
                j += 1
            layers.append(layer)
            i = j
            continue

        if current_section == "ENTITIES" and code == 0:
            entity_type = value.strip()
            entity_data: dict[int, list[str]] = defaultdict(list)
            j = i + 1
            while j < len(pairs):
                c2, v2 = pairs[j]
                if c2 == 0:
                    break
                entity_data[c2].append(v2)
                j += 1

            entity_counts[entity_type] += 1
            layer_name = entity_data.get(8, ["0"])[0].strip()
            entities_by_layer[layer_name] += 1
            collect_entity_bounds(entity_type, entity_data, entity_bounds)

            if entity_type in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
                if entity_type == "MTEXT":
                    value_text = "".join(entity_data.get(1, []) + entity_data.get(3, []))
                else:
                    value_text = "".join(entity_data.get(1, []))
                cleaned = value_text.replace("\\P", "\n").strip()
                if cleaned:
                    texts.append(cleaned)

            length = entity_length(entity_type, entity_data)
            if length is not None:
                length_by_type[entity_type] += length
                length_entity_counts[entity_type] += 1

            i = j
            continue

        i += 1

    info["layers"] = layers
    info["text"]["values"] = texts
    info["text"]["unique_values"] = sorted(set(texts))
    info["text"]["count"] = len(texts)

    bounds = bounds_with_sizes(entity_bounds)

    info["entity_summary"]["total_entities"] = sum(entity_counts.values())
    info["entity_summary"]["entity_counts"] = dict(sorted(entity_counts.items()))
    info["entity_summary"]["entities_by_layer"] = dict(sorted(entities_by_layer.items()))
    info["entity_summary"]["bounds_from_entities"] = bounds
    info["entity_summary"]["estimated_total_entity_length"] = sum(length_by_type.values())
    info["entity_summary"]["estimated_length_by_type"] = dict(sorted(length_by_type.items()))
    info["entity_summary"]["estimated_length_entity_counts"] = dict(sorted(length_entity_counts.items()))

    header = info["header"]
    info["header"] = {
        "acad_version": header.get("$ACADVER"),
        "code_page": header.get("$DWGCODEPAGE"),
        "insbase": header.get("$INSBASE"),
        "extmin": header.get("$EXTMIN"),
        "extmax": header.get("$EXTMAX"),
        "limmin": header.get("$LIMMIN"),
        "limmax": header.get("$LIMMAX"),
    }

    info["sections_present"] = sorted(set(info["sections_present"]))
    return info


def format_report(info: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("DXF Summary")
    lines.append("===========")
    lines.append(f"File: {info['filename']}")
    lines.append(f"Path: {info['path']}")
    lines.append(f"File size: {info['file_size_bytes']:,} bytes")
    lines.append(f"Kind: {info['dxf_kind']}")
    lines.append("")

    lines.append("Header")
    lines.append("------")
    for key, value in info["header"].items():
        lines.append(f"{key}: {value}")
    lines.append("")

    lines.append("Sections present")
    lines.append("----------------")
    for section in info["sections_present"]:
        lines.append(section)
    lines.append("")

    lines.append("Layers")
    lines.append("------")
    if info["layers"]:
        for layer in info["layers"]:
            lines.append(
                f"name={layer.get('name')!r}, color={layer.get('color')}, "
                f"linetype={layer.get('linetype')!r}, flags={layer.get('flags')}"
            )
    else:
        lines.append("No layer definitions found")
    lines.append("")

    es = info["entity_summary"]
    lines.append("Entities")
    lines.append("--------")
    lines.append(f"Total entities: {es['total_entities']}")
    for key, value in es["entity_counts"].items():
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("Entities by layer")
    lines.append("-----------------")
    for key, value in es["entities_by_layer"].items():
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("Bounds from entities")
    lines.append("--------------------")
    for key, value in es["bounds_from_entities"].items():
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("Estimated length by type")
    lines.append("------------------------")
    if es["estimated_length_by_type"]:
        for key, value in es["estimated_length_by_type"].items():
            lines.append(f"{key}: {value:.3f}")
        lines.append(f"TOTAL: {es['estimated_total_entity_length']:.3f}")
    else:
        lines.append("No supported length-estimate entities found")
    lines.append("")
    lines.append("Text values")
    lines.append("-----------")
    if info["text"]["values"]:
        for item in info["text"]["values"]:
            lines.append(repr(item))
    else:
        lines.append("No text found")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract useful information from a DXF file.")
    parser.add_argument("filename", help="Path to the DXF file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    path = Path(args.filename)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    info = parse_dxf(path)
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        print(format_report(info))


if __name__ == "__main__":
    main()
    pdb.set_trace()
