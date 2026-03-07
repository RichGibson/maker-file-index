#!/usr/bin/env python3
"""
Extract useful information from an OpenSCAD (.scad) file.

Usage:
    python scad_extract.py input.scad
    python scad_extract.py input.scad --json
"""

from __future__ import annotations

import argparse
import json
import pdb
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ASSIGNMENT_RE = re.compile(
    r'^\s*([A-Za-z_]\w*)\s*=\s*([^;]+);(?:\s*//\s*(.*))?\s*$',
    re.MULTILINE,
)

MODULE_RE = re.compile(
    r'^\s*module\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{',
    re.MULTILINE,
)

CALL_RE = re.compile(r'(?<!module\s)\b([A-Za-z_]\w*)\s*\(')

INCLUDE_RE = re.compile(r'^\s*(include|use)\s*<([^>]+)>\s*;?', re.MULTILINE)

STRING_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
LINE_COMMENT_RE = re.compile(r'//(.*)$', re.MULTILINE)
BLOCK_COMMENT_RE = re.compile(r'/\*(.*?)\*/', re.DOTALL)


PRIMITIVES = {
    "cube",
    "sphere",
    "cylinder",
    "polyhedron",
    "polygon",
    "circle",
    "square",
    "text",
    "surface",
    "import",
}


TRANSFORMS = {
    "translate",
    "rotate",
    "scale",
    "resize",
    "mirror",
    "multmatrix",
    "color",
    "offset",
    "minkowski",
    "hull",
    "projection",
    "linear_extrude",
    "rotate_extrude",
    "render",
}


CSG_OPS = {
    "union",
    "difference",
    "intersection",
}


CONTROL_WORDS = {
    "if",
    "for",
    "each",
    "let",
    "assert",
    "echo",
    "assign",
    "children",
}


def strip_comments(text: str) -> str:
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
    return text


def safe_number(value: str) -> float | int | None:
    value = value.strip()
    if re.fullmatch(r'[-+]?\d+', value):
        try:
            return int(value)
        except Exception:
            return None
    if re.fullmatch(r'[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?', value):
        try:
            return float(value)
        except Exception:
            return None
    return None


def infer_parameter_values(assignments: dict[str, Any]) -> dict[str, Any]:
    inferred: dict[str, Any] = {}

    keys = [
        "base_width", "base_height", "base_depth",
        "middle_width", "middle_height", "middle_depth",
        "cradle_inner_diameter", "cradle_outer_diameter", "cradle_depth", "cradle_angle",
        "total_height", "$fn",
    ]
    for key in keys:
        if key in assignments:
            raw = assignments[key]["value"]
            num = safe_number(raw)
            inferred[key] = num if num is not None else raw

    if "base_width" in inferred and "base_height" in inferred and "base_depth" in inferred:
        bw = inferred["base_width"]
        bh = inferred["base_height"]
        bd = inferred["base_depth"]
        if all(isinstance(v, (int, float)) for v in (bw, bh, bd)):
            inferred["base_size"] = [bw, bh, bd]

    if "middle_width" in inferred and "middle_height" in inferred and "middle_depth" in inferred:
        mw = inferred["middle_width"]
        mh = inferred["middle_height"]
        md = inferred["middle_depth"]
        if all(isinstance(v, (int, float)) for v in (mw, mh, md)):
            inferred["middle_size"] = [mw, mh, md]

    if "cradle_inner_diameter" in inferred:
        cid = inferred["cradle_inner_diameter"]
        if isinstance(cid, (int, float)):
            inferred["cradle_inner_radius"] = cid / 2

    if "cradle_outer_diameter" in inferred:
        cod = inferred["cradle_outer_diameter"]
        if isinstance(cod, (int, float)):
            inferred["cradle_outer_radius"] = cod / 2

    if "base_height" in inferred and "middle_height" in inferred:
        bh = inferred["base_height"]
        mh = inferred["middle_height"]
        if all(isinstance(v, (int, float)) for v in (bh, mh)):
            inferred["recomputed_total_height"] = bh + mh

    return inferred


def extract_scad(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    text_no_comments = strip_comments(text)

    line_comments = [m.strip() for m in LINE_COMMENT_RE.findall(text) if m.strip()]
    block_comments = [m.strip() for m in BLOCK_COMMENT_RE.findall(text) if m.strip()]
    strings = STRING_RE.findall(text)

    assignments: dict[str, Any] = {}
    for match in ASSIGNMENT_RE.finditer(text):
        name, value, trailing_comment = match.groups()
        assignments[name] = {
            "value": value.strip(),
            "numeric_value": safe_number(value.strip()),
            "comment": trailing_comment.strip() if trailing_comment else None,
        }

    modules = []
    for match in MODULE_RE.finditer(text):
        name, params = match.groups()
        param_list = [p.strip() for p in params.split(",") if p.strip()]
        modules.append({"name": name, "parameters": param_list})

    calls = Counter()
    for name in CALL_RE.findall(text_no_comments):
        calls[name] += 1

    module_names = {m["name"] for m in modules}
    primitive_counts = {name: calls.get(name, 0) for name in sorted(PRIMITIVES) if calls.get(name, 0)}
    transform_counts = {name: calls.get(name, 0) for name in sorted(TRANSFORMS) if calls.get(name, 0)}
    csg_counts = {name: calls.get(name, 0) for name in sorted(CSG_OPS) if calls.get(name, 0)}

    custom_module_calls = {
        name: count
        for name, count in sorted(calls.items())
        if name in module_names
    }

    top_level_invocations = []
    for name in sorted(module_names):
        pattern = re.compile(r'^\s*' + re.escape(name) + r'\s*\(', re.MULTILINE)
        for m in pattern.finditer(text_no_comments):
            line_number = text_no_comments[:m.start()].count("\n") + 1
            top_level_invocations.append({"name": name, "line": line_number})

    includes = [{"kind": kind, "target": target} for kind, target in INCLUDE_RE.findall(text)]

    inferred = infer_parameter_values(assignments)

    result: dict[str, Any] = {
        "file": str(path),
        "filename": path.name,
        "file_size_bytes": path.stat().st_size,
        "format": "OpenSCAD",
        "line_count": text.count("\n") + 1,
        "character_count": len(text),
        "assignments": assignments,
        "modules": modules,
        "includes": includes,
        "primitive_counts": primitive_counts,
        "transform_counts": transform_counts,
        "csg_counts": csg_counts,
        "custom_module_calls": custom_module_calls,
        "line_comments": line_comments,
        "block_comments": block_comments,
        "strings": strings,
        "top_level_invocations": top_level_invocations,
        "inferred_values": inferred,
    }
    return result


def format_report(info: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("OpenSCAD Summary")
    lines.append("================")
    lines.append(f"File: {info['filename']}")
    lines.append(f"Path: {info['file']}")
    lines.append(f"File size: {info['file_size_bytes']:,} bytes")
    lines.append(f"Lines: {info['line_count']}")
    lines.append(f"Characters: {info['character_count']}")
    lines.append("")

    lines.append("Includes / Uses")
    lines.append("---------------")
    if info["includes"]:
        for item in info["includes"]:
            lines.append(f"{item['kind']} <{item['target']}>")
    else:
        lines.append("None")
    lines.append("")

    lines.append("Assignments")
    lines.append("-----------")
    if info["assignments"]:
        for name in sorted(info["assignments"]):
            item = info["assignments"][name]
            lines.append(
                f"{name} = {item['value']}"
                + (f"    // {item['comment']}" if item["comment"] else "")
            )
    else:
        lines.append("None")
    lines.append("")

    lines.append("Modules")
    lines.append("-------")
    if info["modules"]:
        for module in info["modules"]:
            params = ", ".join(module["parameters"])
            lines.append(f"{module['name']}({params})")
    else:
        lines.append("None")
    lines.append("")

    lines.append("Primitive counts")
    lines.append("----------------")
    if info["primitive_counts"]:
        for name, count in info["primitive_counts"].items():
            lines.append(f"{name}: {count}")
    else:
        lines.append("None")
    lines.append("")

    lines.append("Transform counts")
    lines.append("----------------")
    if info["transform_counts"]:
        for name, count in info["transform_counts"].items():
            lines.append(f"{name}: {count}")
    else:
        lines.append("None")
    lines.append("")

    lines.append("CSG counts")
    lines.append("----------")
    if info["csg_counts"]:
        for name, count in info["csg_counts"].items():
            lines.append(f"{name}: {count}")
    else:
        lines.append("None")
    lines.append("")

    lines.append("Custom module calls")
    lines.append("-------------------")
    if info["custom_module_calls"]:
        for name, count in info["custom_module_calls"].items():
            lines.append(f"{name}: {count}")
    else:
        lines.append("None")
    lines.append("")

    lines.append("Comments")
    lines.append("--------")
    comments = info["line_comments"] + info["block_comments"]
    if comments:
        for item in comments:
            lines.append(item)
    else:
        lines.append("None")
    lines.append("")

    lines.append("Strings")
    lines.append("-------")
    if info["strings"]:
        for item in info["strings"]:
            lines.append(repr(item))
    else:
        lines.append("None")
    lines.append("")

    lines.append("Inferred values")
    lines.append("---------------")
    if info["inferred_values"]:
        for name, value in info["inferred_values"].items():
            lines.append(f"{name}: {value}")
    else:
        lines.append("None")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract useful information from an OpenSCAD file.")
    parser.add_argument("filename", help="Path to the .scad file")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a text report")
    args = parser.parse_args()

    path = Path(args.filename)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    info = extract_scad(path)

    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        print(format_report(info))


if __name__ == "__main__":
    main()
    pdb.set_trace()
