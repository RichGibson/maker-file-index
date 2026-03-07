#!/usr/bin/env python3
"""Extract useful information from a LightBurn .lbrn2 file.

This utility:
- extracts notes and all visible text strings
- summarizes cut settings and shape counts
- estimates cut/engrave time from path lengths and layer speeds

Notes on the estimate:
- line geometry is measured directly
- bezier curves are approximated from sampled control points
- text time is estimated from backup paths when present
- non-output layers are excluded
- travel moves, acceleration, corner slowdowns, lead-ins, and controller overhead
  are not modeled exactly, so the estimate is approximate
"""

from __future__ import annotations

import argparse
import json
import math
import pdb
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


VERTEX_RE = re.compile(r"V([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
PRIM_RE = re.compile(r"([LB])(\d+)\s+(\d+)")


@dataclass
class CutSetting:
    index: int
    name: str | None
    cut_type: str | None
    speed: float | None
    num_passes: int
    do_output: bool
    min_power: float | None = None
    max_power: float | None = None
    priority: int | None = None
    interval: float | None = None


@dataclass
class LayerEstimate:
    cut_index: int
    name: str | None
    speed_mm_s: float | None
    passes: int
    do_output: bool
    path_count: int
    length_mm: float
    active_length_mm: float
    time_seconds_raw: float | None
    time_seconds_with_overhead: float | None


@dataclass
class EstimateReport:
    total_active_length_mm: float
    total_time_seconds_raw: float
    total_time_seconds_with_overhead: float
    layer_estimates: list[LayerEstimate]
    assumptions: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract useful information from a LightBurn .lbrn2 XML file.")
    parser.add_argument("filename", help="Path to the .lbrn2 file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of a human-readable report",
    )
    parser.add_argument(
        "--overhead-factor",
        type=float,
        default=1.15,
        help="Multiply raw cut time by this factor to account for travel and machine overhead (default: 1.15)",
    )
    return parser.parse_args()


def parse_transform(text: str | None) -> tuple[float, float, float, float, float, float]:
    if not text:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    values = [float(part) for part in text.split()]
    if len(values) != 6:
        raise ValueError(f"Expected 6 transform values, got {len(values)} from {text!r}")
    return tuple(values)  # type: ignore[return-value]


def apply_transform(point: tuple[float, float], xform: tuple[float, float, float, float, float, float]) -> tuple[float, float]:
    a, b, c, d, e, f = xform
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def parse_vertices(text: str | None) -> list[tuple[float, float]]:
    if not text:
        return []
    return [(float(match.group(1)), float(match.group(2))) for match in VERTEX_RE.finditer(text)]


def cubic_bezier_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    u = 1.0 - t
    x = (u ** 3) * p0[0] + 3 * (u ** 2) * t * p1[0] + 3 * u * (t ** 2) * p2[0] + (t ** 3) * p3[0]
    y = (u ** 3) * p0[1] + 3 * (u ** 2) * t * p1[1] + 3 * u * (t ** 2) * p2[1] + (t ** 3) * p3[1]
    return (x, y)


def cubic_bezier_length(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 24,
) -> float:
    points = [cubic_bezier_point(p0, p1, p2, p3, step / steps) for step in range(steps + 1)]
    return sum(math.dist(left, right) for left, right in zip(points, points[1:]))


def parse_primitives(text: str | None) -> list[tuple[str, int, int]]:
    if not text:
        return []
    return [(kind, int(start), int(end)) for kind, start, end in PRIM_RE.findall(text)]


def shape_path_length(path_element: ET.Element) -> float:
    xform = parse_transform(path_element.findtext("XForm"))
    vertices = [apply_transform(vertex, xform) for vertex in parse_vertices(path_element.findtext("VertList"))]
    primitive_text = (path_element.findtext("PrimList") or "").strip()
    primitives = parse_primitives(primitive_text)

    if not vertices:
        return 0.0

    if not primitives:
        # Fallback for very simple paths with no primitive list.
        return sum(math.dist(left, right) for left, right in zip(vertices, vertices[1:]))

    length_mm = 0.0
    for kind, start, end in primitives:
        if kind == "L":
            if start < len(vertices) and end < len(vertices):
                length_mm += math.dist(vertices[start], vertices[end])
        elif kind == "B":
            # LightBurn stores cubic segments as consecutive B records whose end points walk through the control points.
            # A simple and usually good approximation is to interpret Bn n+1 groups in chunks of 3 after a current point.
            # When the indices do not fit that pattern cleanly, fall back to straight-line distance between endpoints.
            if start + 3 < len(vertices) and end == start + 1:
                # Defer grouped handling below when possible.
                continue
            if start < len(vertices) and end < len(vertices):
                length_mm += math.dist(vertices[start], vertices[end])

    # Better handling for common cubic chains.
    i = 0
    while i < len(primitives):
        kind, start, end = primitives[i]
        if kind != "B":
            i += 1
            continue
        chain = [primitives[i]]
        j = i + 1
        while j < len(primitives) and primitives[j][0] == "B":
            chain.append(primitives[j])
            j += 1

        # Typical cubic chain: B0 1 B1 2 B2 3 [next segment starts B3 4 B4 5 B5 6 ...]
        if len(chain) >= 3:
            k = 0
            while k + 2 < len(chain):
                a = chain[k]
                b = chain[k + 1]
                c = chain[k + 2]
                if a[2] == a[1] + 1 and b[1] == a[2] and c[1] == b[2] and c[2] == c[1] + 1:
                    p0_index = a[1]
                    p1_index = a[2]
                    p2_index = b[2]
                    p3_index = c[2]
                    if p3_index < len(vertices):
                        length_mm += cubic_bezier_length(
                            vertices[p0_index],
                            vertices[p1_index],
                            vertices[p2_index],
                            vertices[p3_index],
                        )
                        k += 3
                        continue
                # Fallback if the chain does not match the common cubic pattern.
                if a[1] < len(vertices) and a[2] < len(vertices):
                    length_mm += math.dist(vertices[a[1]], vertices[a[2]])
                k += 1
            # Handle leftovers in the chain.
            while k < len(chain):
                seg = chain[k]
                if seg[1] < len(vertices) and seg[2] < len(vertices):
                    length_mm += math.dist(vertices[seg[1]], vertices[seg[2]])
                k += 1
        else:
            for seg in chain:
                if seg[1] < len(vertices) and seg[2] < len(vertices):
                    length_mm += math.dist(vertices[seg[1]], vertices[seg[2]])
        i = j

    return length_mm


def iter_all_shapes(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if element.tag == "Shape":
            yield element


def iter_all_paths(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if element.tag == "Shape" and element.attrib.get("Type") == "Path":
            yield element
        elif element.tag == "BackupPath" and element.attrib.get("Type") == "Path":
            yield element


def read_child_value(element: ET.Element, tag_name: str, default: str | None = None) -> str | None:
    child = element.find(tag_name)
    if child is None:
        return default
    return child.attrib.get("Value", default)


def parse_cut_settings(root: ET.Element) -> dict[int, CutSetting]:
    settings: dict[int, CutSetting] = {}
    for element in root.findall("CutSetting"):
        index_text = read_child_value(element, "index")
        if index_text is None:
            continue
        index = int(index_text)
        settings[index] = CutSetting(
            index=index,
            name=read_child_value(element, "name"),
            cut_type=element.attrib.get("type"),
            speed=float(read_child_value(element, "speed", "0") or 0),
            num_passes=int(read_child_value(element, "numPasses", "1") or 1),
            do_output=(read_child_value(element, "doOutput", "1") != "0"),
            min_power=float(read_child_value(element, "minPower", "0") or 0),
            max_power=float(read_child_value(element, "maxPower", "0") or 0),
            priority=int(read_child_value(element, "priority", "0") or 0),
            interval=(float(read_child_value(element, "interval")) if read_child_value(element, "interval") is not None else None),
        )
    return settings


def collect_text(root: ET.Element) -> list[str]:
    values: list[str] = []
    for shape in iter_all_shapes(root):
        if shape.attrib.get("Type") == "Text":
            text = shape.attrib.get("Str")
            if text:
                values.append(text)
    return values


def summarize_shapes(root: ET.Element) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for shape in iter_all_shapes(root):
        counts[shape.attrib.get("Type", "Unknown")] += 1
    return dict(counts)


def estimate_cut_time(root: ET.Element, cut_settings: dict[int, CutSetting], overhead_factor: float) -> EstimateReport:
    layer_lengths: dict[int, float] = defaultdict(float)
    layer_counts: dict[int, int] = defaultdict(int)

    for path_element in iter_all_paths(root):
        cut_index_text = path_element.attrib.get("CutIndex")
        if cut_index_text is None:
            continue
        cut_index = int(cut_index_text)
        layer_lengths[cut_index] += shape_path_length(path_element)
        layer_counts[cut_index] += 1

    layer_estimates: list[LayerEstimate] = []
    total_active_length = 0.0
    total_raw_seconds = 0.0
    total_with_overhead_seconds = 0.0

    for cut_index in sorted(layer_lengths):
        setting = cut_settings.get(
            cut_index,
            CutSetting(
                index=cut_index,
                name=None,
                cut_type=None,
                speed=None,
                num_passes=1,
                do_output=True,
            ),
        )
        length_mm = layer_lengths[cut_index]
        passes = max(setting.num_passes, 1)
        active_length_mm = length_mm * passes if setting.do_output else 0.0
        raw_seconds = None
        overhead_seconds = None
        if setting.do_output and setting.speed and setting.speed > 0:
            raw_seconds = active_length_mm / setting.speed
            overhead_seconds = raw_seconds * overhead_factor
            total_active_length += active_length_mm
            total_raw_seconds += raw_seconds
            total_with_overhead_seconds += overhead_seconds

        layer_estimates.append(
            LayerEstimate(
                cut_index=cut_index,
                name=setting.name,
                speed_mm_s=setting.speed,
                passes=passes,
                do_output=setting.do_output,
                path_count=layer_counts[cut_index],
                length_mm=length_mm,
                active_length_mm=active_length_mm,
                time_seconds_raw=raw_seconds,
                time_seconds_with_overhead=overhead_seconds,
            )
        )

    assumptions = [
        "Layer speed is interpreted as mm/s.",
        "numPasses multiplies cut distance.",
        "Layers with doOutput=0 are excluded from the final active-time estimate.",
        "Bezier curves are approximated numerically from control points.",
        f"A machine-overhead multiplier of {overhead_factor:.2f} is applied to the raw estimate.",
        "This does not model controller optimization order, acceleration limits, lead-ins, or manual setup time.",
    ]

    return EstimateReport(
        total_active_length_mm=total_active_length,
        total_time_seconds_raw=total_raw_seconds,
        total_time_seconds_with_overhead=total_with_overhead_seconds,
        layer_estimates=layer_estimates,
        assumptions=assumptions,
    )


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:d}h {minutes:d}m {remaining_seconds:0.1f}s"
    return f"{int(minutes):d}m {remaining_seconds:0.1f}s"


def extract_notes(filename: str) -> dict[str, object]:
    root = ET.parse(filename).getroot()
    cut_settings = parse_cut_settings(root)
    text_strings = collect_text(root)
    notes_text = ""
    notes_element = root.find("Notes")
    if notes_element is not None:
        notes_text = notes_element.attrib.get("Notes", "")

    report = {
        "file": str(Path(filename)),
        "project_metadata": {
            "AppVersion": root.attrib.get("AppVersion"),
            "DeviceName": root.attrib.get("DeviceName"),
            "FormatVersion": root.attrib.get("FormatVersion"),
            "MaterialHeight": root.attrib.get("MaterialHeight"),
            "MirrorX": root.attrib.get("MirrorX"),
            "MirrorY": root.attrib.get("MirrorY"),
        },
        "notes": notes_text,
        "text_strings": text_strings,
        "unique_text_strings": sorted(set(text_strings), key=str.casefold),
        "shape_counts": summarize_shapes(root),
        "cut_settings": [asdict(setting) for _, setting in sorted(cut_settings.items())],
    }
    return report


def build_full_report(filename: str, overhead_factor: float) -> dict[str, object]:
    root = ET.parse(filename).getroot()
    cut_settings = parse_cut_settings(root)
    extract = extract_notes(filename)
    estimate = estimate_cut_time(root, cut_settings, overhead_factor)
    extract["time_estimate"] = {
        "total_active_length_mm": estimate.total_active_length_mm,
        "total_time_seconds_raw": estimate.total_time_seconds_raw,
        "total_time_seconds_with_overhead": estimate.total_time_seconds_with_overhead,
        "assumptions": estimate.assumptions,
        "layers": [asdict(layer) for layer in estimate.layer_estimates],
    }
    return extract


def print_human_report(report: dict[str, object]) -> None:
    print(f"File: {report['file']}")
    print()

    print("Project metadata:")
    for key, value in report["project_metadata"].items():
        print(f"  {key}: {value}")
    print()

    print("Notes:")
    notes = str(report.get("notes", "")).rstrip()
    if notes:
        for line in notes.splitlines():
            print(f"  {line}")
    else:
        print("  <none>")
    print()

    print("Text strings:")
    text_strings = report.get("text_strings", [])
    if text_strings:
        for item in text_strings:
            print(f"  {item}")
    else:
        print("  <none>")
    print()

    print("Shape counts:")
    for key, value in sorted(report.get("shape_counts", {}).items()):
        print(f"  {key}: {value}")
    print()

    print("Cut settings:")
    for setting in report.get("cut_settings", []):
        print(
            "  "
            f"index={setting['index']} "
            f"name={setting['name']} "
            f"speed={setting['speed']} mm/s "
            f"passes={setting['num_passes']} "
            f"do_output={setting['do_output']}"
        )
    print()

    time_estimate = report.get("time_estimate")
    if isinstance(time_estimate, dict):
        print("Estimated machine time:")
        print(f"  Total active length: {time_estimate['total_active_length_mm']:.2f} mm")
        print(f"  Raw time: {format_seconds(float(time_estimate['total_time_seconds_raw']))}")
        print(
            "  Raw time with overhead: "
            f"{format_seconds(float(time_estimate['total_time_seconds_with_overhead']))}"
        )
        print()
        print("  By layer:")
        for layer in time_estimate.get("layers", []):
            print(
                "    "
                f"CutIndex {layer['cut_index']}: "
                f"name={layer['name']} "
                f"length={layer['length_mm']:.2f} mm "
                f"active_length={layer['active_length_mm']:.2f} mm "
                f"speed={layer['speed_mm_s']} mm/s "
                f"passes={layer['passes']} "
                f"do_output={layer['do_output']} "
                f"raw={format_seconds(layer['time_seconds_raw'])} "
                f"with_overhead={format_seconds(layer['time_seconds_with_overhead'])}"
            )
        print()
        print("  Assumptions:")
        for assumption in time_estimate.get("assumptions", []):
            print(f"    - {assumption}")


if __name__ == "__main__":
    args = parse_args()
    report = build_full_report(args.filename, args.overhead_factor)
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_human_report(report)
    pdb.set_trace()
