#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import pdb
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


VERT_RE = re.compile(
    r"V(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)"
)

MATRIX_RE = re.compile(
    r"^\s*"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s*$"
)


@dataclass
class CutSetting:
    index: int
    name: str
    layer_type: str
    speed: float | None
    num_passes: int = 1
    do_output: bool = True
    interval: float | None = None
    overscan: float | None = None
    scan_opt: str | None = None
    raw_values: dict[str, str] = field(default_factory=dict)


@dataclass
class PathStats:
    cut_length_mm: float = 0.0
    travel_mm: float = 0.0
    num_paths: int = 0
    num_corners: int = 0
    num_short_segments: int = 0
    time_seconds: float = 0.0


@dataclass
class RasterObject:
    label: str
    bbox_width_mm: float
    bbox_height_mm: float
    scan_lines: int
    scan_distance_mm: float
    time_seconds: float


@dataclass
class RasterStats:
    bbox_width_mm: float = 0.0
    bbox_height_mm: float = 0.0
    scan_gap_mm: float = 0.1
    overscan_mm: float = 0.0
    scan_lines: int = 0
    scan_distance_mm: float = 0.0
    time_seconds: float = 0.0
    objects: list[RasterObject] = field(default_factory=list)


@dataclass
class LayerEstimate:
    cut_index: int
    layer_name: str
    layer_type: str
    speed: float | None
    num_passes: int
    do_output: bool
    vector: PathStats = field(default_factory=PathStats)
    raster: RasterStats = field(default_factory=RasterStats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate LightBurn .lbrn2 job time with improved vector and raster handling."
    )
    parser.add_argument("filename", type=Path, help="Path to LightBurn .lbrn2 file")
    parser.add_argument(
        "--speed-unit",
        choices=("mm_s", "mm_min"),
        default="mm_s",
        help="Interpret LightBurn speed values as mm/s or mm/min",
    )
    parser.add_argument(
        "--travel-speed",
        type=float,
        default=200.0,
        help="Travel speed in mm/s for non-cut moves",
    )
    parser.add_argument(
        "--path-overhead",
        type=float,
        default=0.12,
        help="Seconds added per vector path",
    )
    parser.add_argument(
        "--corner-overhead",
        type=float,
        default=0.03,
        help="Seconds added per sharp corner",
    )
    parser.add_argument(
        "--short-segment-threshold",
        type=float,
        default=3.0,
        help="Segments shorter than this are penalized",
    )
    parser.add_argument(
        "--short-segment-penalty-factor",
        type=float,
        default=0.45,
        help="Short segments run at this fraction of nominal speed",
    )
    parser.add_argument(
        "--default-raster-efficiency",
        type=float,
        default=0.70,
        help="Fallback raster effective speed factor",
    )
    parser.add_argument(
        "--include-disabled-layers",
        action="store_true",
        help="Include layers with doOutput=0 in the estimate",
    )
    parser.add_argument(
        "--show-raster-objects",
        action="store_true",
        help="Print per-object raster estimates",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print parse diagnostics",
    )
    return parser.parse_args()


def try_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def try_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def speed_to_mm_s(speed: float | None, speed_unit: str) -> float | None:
    if speed is None or speed <= 0:
        return None
    if speed_unit == "mm_s":
        return speed
    return speed / 60.0


def load_root(path: Path) -> ET.Element:
    tree = ET.parse(path)
    return tree.getroot()


def extract_value_map(elem: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in elem:
        value = child.attrib.get("Value")
        if value is not None:
            values[child.tag] = value
    return values


def parse_cut_settings(root: ET.Element) -> dict[int, CutSetting]:
    settings: dict[int, CutSetting] = {}

    for cut in root.findall("CutSetting"):
        values = extract_value_map(cut)
        index = try_int(values.get("index"), default=-1)
        if index < 0:
            continue

        settings[index] = CutSetting(
            index=index,
            name=values.get("name", f"Layer {index}"),
            layer_type=cut.attrib.get("type", "Cut"),
            speed=try_float(values.get("speed")),
            num_passes=max(1, try_int(values.get("numPasses"), default=1)),
            do_output=values.get("doOutput", "1") != "0",
            interval=try_float(values.get("interval")),
            overscan=try_float(values.get("overscan")),
            scan_opt=values.get("scanOpt"),
            raw_values=values,
        )

    return settings


def parse_xform(elem: ET.Element) -> tuple[float, float, float, float, float, float]:
    xform_text = (elem.findtext("XForm", default="") or "").strip()
    if not xform_text:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    match = MATRIX_RE.match(xform_text)
    if not match:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    return tuple(float(group) for group in match.groups())  # type: ignore[return-value]


def apply_xform(
    point: tuple[float, float],
    matrix: tuple[float, float, float, float, float, float],
) -> tuple[float, float]:
    x, y = point
    a, b, c, d, tx, ty = matrix
    return (a * x + c * y + tx, b * x + d * y + ty)


def parse_vertlist_points(
    elem: ET.Element,
) -> list[tuple[float, float]]:
    vert_text = elem.findtext("VertList", default="") or ""
    matrix = parse_xform(elem)
    points: list[tuple[float, float]] = []

    for match in VERT_RE.finditer(vert_text):
        x = float(match.group("x"))
        y = float(match.group("y"))
        points.append(apply_xform((x, y), matrix))

    return points


def same_point(
    p1: tuple[float, float],
    p2: tuple[float, float],
    tol: float = 1e-6,
) -> bool:
    return abs(p1[0] - p2[0]) <= tol and abs(p1[1] - p2[1]) <= tol


def path_is_closed(shape: ET.Element, points: list[tuple[float, float]]) -> bool:
    prim_text = (shape.findtext("PrimList", default="") or "").lower()
    if "closed" in prim_text:
        return True
    if len(points) >= 2 and same_point(points[0], points[-1]):
        return True
    return False


def bbox_from_points(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_union(
    a: tuple[float, float, float, float] | None,
    b: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float] | None:
    if a is None:
        return b
    if b is None:
        return a
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    )


def polyline_length(points: list[tuple[float, float]], closed: bool) -> float:
    if len(points) < 2:
        return 0.0

    total = 0.0
    for p1, p2 in zip(points, points[1:]):
        total += math.dist(p1, p2)

    if closed and not same_point(points[0], points[-1]):
        total += math.dist(points[-1], points[0])

    return total


def angle_between_segments_degrees(
    p_prev: tuple[float, float],
    p_curr: tuple[float, float],
    p_next: tuple[float, float],
) -> float | None:
    ax = p_curr[0] - p_prev[0]
    ay = p_curr[1] - p_prev[1]
    bx = p_next[0] - p_curr[0]
    by = p_next[1] - p_curr[1]

    mag_a = math.hypot(ax, ay)
    mag_b = math.hypot(bx, by)
    if mag_a < 1e-9 or mag_b < 1e-9:
        return None

    dot = ax * bx + ay * by
    cos_theta = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
    return math.degrees(math.acos(cos_theta))


def count_sharp_corners(
    points: list[tuple[float, float]],
    closed: bool,
    threshold_degrees: float = 150.0,
) -> int:
    if len(points) < 3:
        return 0

    count = 0

    if closed:
        ring = points[:]
        if same_point(ring[0], ring[-1]):
            ring = ring[:-1]
        n = len(ring)
        for i in range(n):
            angle = angle_between_segments_degrees(
                ring[(i - 1) % n],
                ring[i],
                ring[(i + 1) % n],
            )
            if angle is not None and angle < threshold_degrees:
                count += 1
        return count

    for i in range(1, len(points) - 1):
        angle = angle_between_segments_degrees(
            points[i - 1],
            points[i],
            points[i + 1],
        )
        if angle is not None and angle < threshold_degrees:
            count += 1

    return count


def estimate_vector_path_time(
    points: list[tuple[float, float]],
    closed: bool,
    speed_mm_s: float,
    short_segment_threshold: float,
    short_segment_penalty_factor: float,
) -> tuple[float, int]:
    if len(points) < 2:
        return (0.0, 0)

    pairs = list(zip(points, points[1:]))
    if closed and not same_point(points[0], points[-1]):
        pairs.append((points[-1], points[0]))

    total_time = 0.0
    short_segments = 0

    for p1, p2 in pairs:
        seg_len = math.dist(p1, p2)
        if seg_len <= 0:
            continue

        if seg_len < short_segment_threshold:
            effective_speed = max(speed_mm_s * short_segment_penalty_factor, 1e-9)
            short_segments += 1
        else:
            effective_speed = speed_mm_s

        total_time += seg_len / effective_speed

    return (total_time, short_segments)


def is_raster_layer(setting: CutSetting) -> bool:
    if setting.interval is not None:
        return True
    if setting.scan_opt:
        return True
    if setting.overscan is not None:
        return True

    name_lower = setting.name.lower()
    if "interval" in name_lower or "scan" in name_lower or "fill" in name_lower:
        return True

    layer_type_lower = setting.layer_type.lower()
    if "fill" in layer_type_lower or "image" in layer_type_lower or "scan" in layer_type_lower:
        return True

    return False


def raster_efficiency_for_setting(setting: CutSetting, default_efficiency: float) -> float:
    scan_opt = (setting.scan_opt or "").strip().lower()

    if scan_opt == "individual":
        return min(default_efficiency, 0.60)

    if scan_opt in {"bi", "bidirectional"}:
        return max(default_efficiency, 0.75)

    return default_efficiency


def estimate_raster_object(
    label: str,
    bbox: tuple[float, float, float, float],
    speed_mm_s: float,
    scan_gap_mm: float,
    overscan_mm: float,
    efficiency: float,
) -> RasterObject:
    min_x, min_y, max_x, max_y = bbox
    width_mm = max(0.0, max_x - min_x)
    height_mm = max(0.0, max_y - min_y)

    scan_lines = max(1, math.ceil(height_mm / max(scan_gap_mm, 1e-9)))
    scan_line_length = width_mm + (2.0 * overscan_mm)
    total_scan_distance = scan_lines * scan_line_length
    effective_speed = max(speed_mm_s * efficiency, 1e-9)
    time_seconds = total_scan_distance / effective_speed

    return RasterObject(
        label=label,
        bbox_width_mm=width_mm,
        bbox_height_mm=height_mm,
        scan_lines=scan_lines,
        scan_distance_mm=total_scan_distance,
        time_seconds=time_seconds,
    )


def iter_shapes(elem: ET.Element):
    for child in elem:
        if child.tag == "Shape":
            yield child
            yield from iter_shapes(child)
        else:
            yield from iter_shapes(child)


def get_or_create_layer(
    estimates: dict[int, LayerEstimate],
    setting: CutSetting,
) -> LayerEstimate:
    layer = estimates.get(setting.index)
    if layer is None:
        layer = LayerEstimate(
            cut_index=setting.index,
            layer_name=setting.name,
            layer_type=setting.layer_type,
            speed=setting.speed,
            num_passes=setting.num_passes,
            do_output=setting.do_output,
        )
        estimates[setting.index] = layer
    return layer


def estimate_job(
    root: ET.Element,
    settings: dict[int, CutSetting],
    speed_unit: str,
    travel_speed: float,
    path_overhead: float,
    corner_overhead: float,
    short_segment_threshold: float,
    short_segment_penalty_factor: float,
    default_raster_efficiency: float,
    include_disabled_layers: bool,
    verbose: bool,
) -> dict[int, LayerEstimate]:
    estimates: dict[int, LayerEstimate] = {}
    previous_vector_end: tuple[float, float] | None = None
    layer_raster_bboxes: dict[int, tuple[float, float, float, float] | None] = {}

    for shape in iter_shapes(root):
        cut_index = try_int(shape.attrib.get("CutIndex"), default=-1)
        if cut_index < 0:
            continue

        setting = settings.get(cut_index)
        if setting is None:
            setting = CutSetting(
                index=cut_index,
                name=f"Layer {cut_index}",
                layer_type="Unknown",
                speed=None,
            )

        if not include_disabled_layers and not setting.do_output:
            continue

        speed_mm_s = speed_to_mm_s(setting.speed, speed_unit)
        shape_type = (shape.attrib.get("Type") or "").strip()

        raster_like = is_raster_layer(setting) or shape_type in {"Text", "Image"}

        if raster_like:
            bbox = None

            backup_path = shape.find("BackupPath")
            if backup_path is not None:
                backup_points = parse_vertlist_points(backup_path)
                bbox = bbox_from_points(backup_points)

            if bbox is None:
                shape_points = parse_vertlist_points(shape)
                bbox = bbox_from_points(shape_points)

            if bbox is not None:
                layer_raster_bboxes[cut_index] = bbox_union(
                    layer_raster_bboxes.get(cut_index),
                    bbox,
                )

                if speed_mm_s is not None:
                    layer = get_or_create_layer(estimates, setting)
                    scan_gap_mm = setting.interval if setting.interval is not None else 0.1
                    overscan_mm = setting.overscan if setting.overscan is not None else 0.0
                    efficiency = raster_efficiency_for_setting(
                        setting,
                        default_raster_efficiency,
                    )

                    label = shape.attrib.get("Str", shape_type or "RasterObject")
                    obj = estimate_raster_object(
                        label=label,
                        bbox=bbox,
                        speed_mm_s=speed_mm_s,
                        scan_gap_mm=scan_gap_mm,
                        overscan_mm=overscan_mm,
                        efficiency=efficiency,
                    )
                    layer.raster.objects.append(obj)

                    if verbose:
                        print(
                            f"Raster object layer={cut_index} label={label!r} "
                            f"bbox=({obj.bbox_width_mm:.2f} x {obj.bbox_height_mm:.2f}) "
                            f"lines={obj.scan_lines}"
                        )
            continue

        if shape_type != "Path":
            continue

        points = parse_vertlist_points(shape)
        if len(points) < 2:
            continue

        layer = get_or_create_layer(estimates, setting)
        closed = path_is_closed(shape, points)
        length_mm = polyline_length(points, closed)
        corners = count_sharp_corners(points, closed)

        layer.vector.cut_length_mm += length_mm
        layer.vector.num_paths += 1
        layer.vector.num_corners += corners

        if previous_vector_end is not None:
            layer.vector.travel_mm += math.dist(previous_vector_end, points[0])

        previous_vector_end = points[0] if closed else points[-1]

        if speed_mm_s is not None:
            segment_time, short_segments = estimate_vector_path_time(
                points=points,
                closed=closed,
                speed_mm_s=speed_mm_s,
                short_segment_threshold=short_segment_threshold,
                short_segment_penalty_factor=short_segment_penalty_factor,
            )
            layer.vector.time_seconds += segment_time
            layer.vector.num_short_segments += short_segments

    for cut_index, bbox in layer_raster_bboxes.items():
        layer = estimates.get(cut_index)
        if layer is None or bbox is None:
            continue

        min_x, min_y, max_x, max_y = bbox
        layer.raster.bbox_width_mm = max_x - min_x
        layer.raster.bbox_height_mm = max_y - min_y

    for layer in estimates.values():
        setting = settings.get(layer.cut_index)
        passes = 1 if setting is None else max(1, setting.num_passes)

        vector_extra = (
            (layer.vector.travel_mm / max(travel_speed, 1e-9))
            + (layer.vector.num_paths * path_overhead)
            + (layer.vector.num_corners * corner_overhead)
        )
        layer.vector.time_seconds = (layer.vector.time_seconds + vector_extra) * passes

        if setting is not None:
            layer.raster.scan_gap_mm = setting.interval if setting.interval is not None else 0.1
            layer.raster.overscan_mm = setting.overscan if setting.overscan is not None else 0.0

        layer.raster.scan_lines = sum(obj.scan_lines for obj in layer.raster.objects)
        layer.raster.scan_distance_mm = sum(obj.scan_distance_mm for obj in layer.raster.objects)
        layer.raster.time_seconds = sum(obj.time_seconds for obj in layer.raster.objects) * passes

    return estimates


def format_seconds(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)

    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def print_report(
    filename: Path,
    root: ET.Element,
    settings: dict[int, CutSetting],
    estimates: dict[int, LayerEstimate],
    speed_unit: str,
    show_raster_objects: bool,
) -> None:
    print(f"File: {filename}")
    print(f"AppVersion: {root.attrib.get('AppVersion', 'unknown')}")
    print(f"DeviceName: {root.attrib.get('DeviceName', 'unknown')}")
    print(f"Speed interpretation: {speed_unit}")
    print()

    if not estimates:
        print("No estimable layers found.")
        return

    total_seconds = 0.0

    for cut_index in sorted(estimates):
        layer = estimates[cut_index]
        layer_total = layer.vector.time_seconds + layer.raster.time_seconds
        total_seconds += layer_total

        print(f"Layer {cut_index}: {layer.layer_name}")
        print(f"  Type:           {layer.layer_type}")
        print(f"  Speed:          {layer.speed if layer.speed is not None else 'unknown'}")
        print(f"  Passes:         {layer.num_passes}")
        print(f"  Output:         {'enabled' if layer.do_output else 'disabled'}")

        if layer.vector.num_paths > 0:
            print("  Vector:")
            print(f"    Cut length:   {layer.vector.cut_length_mm:.2f} mm")
            print(f"    Travel:       {layer.vector.travel_mm:.2f} mm")
            print(f"    Paths:        {layer.vector.num_paths}")
            print(f"    Corners:      {layer.vector.num_corners}")
            print(f"    Short segs:   {layer.vector.num_short_segments}")
            print(f"    Time:         {format_seconds(layer.vector.time_seconds)}")

        if layer.raster.objects:
            print("  Raster:")
            print(f"    BBox width:   {layer.raster.bbox_width_mm:.2f} mm")
            print(f"    BBox height:  {layer.raster.bbox_height_mm:.2f} mm")
            print(f"    Scan gap:     {layer.raster.scan_gap_mm:.4f} mm")
            print(f"    Overscan:     {layer.raster.overscan_mm:.2f} mm")
            print(f"    Objects:      {len(layer.raster.objects)}")
            print(f"    Scan lines:   {layer.raster.scan_lines}")
            print(f"    Scan dist:    {layer.raster.scan_distance_mm:.2f} mm")
            print(f"    Time:         {format_seconds(layer.raster.time_seconds)}")

            if show_raster_objects:
                for obj in layer.raster.objects:
                    print(
                        f"      - {obj.label}: "
                        f"{obj.bbox_width_mm:.2f} x {obj.bbox_height_mm:.2f} mm, "
                        f"{obj.scan_lines} lines, "
                        f"{format_seconds(obj.time_seconds)}"
                    )

        print(f"  Layer total:    {format_seconds(layer_total)}")
        print()

    print("Overall")
    print("-------")
    print(f"Estimated total time: {format_seconds(total_seconds)}")
    print()
    print("Notes:")
    print("- Raster-like layers are detected from interval/scan settings and text/image shapes.")
    print("- Text objects use BackupPath geometry when available.")
    print("- Disabled layers are skipped unless --include-disabled-layers is used.")


def main() -> int:
    args = parse_args()

    if not args.filename.exists():
        print(f"File not found: {args.filename}", file=sys.stderr)
        return 1

    root = load_root(args.filename)
    settings = parse_cut_settings(root)

    estimates = estimate_job(
        root=root,
        settings=settings,
        speed_unit=args.speed_unit,
        travel_speed=args.travel_speed,
        path_overhead=args.path_overhead,
        corner_overhead=args.corner_overhead,
        short_segment_threshold=args.short_segment_threshold,
        short_segment_penalty_factor=args.short_segment_penalty_factor,
        default_raster_efficiency=args.default_raster_efficiency,
        include_disabled_layers=args.include_disabled_layers,
        verbose=args.verbose,
    )

    print_report(
        filename=args.filename,
        root=root,
        settings=settings,
        estimates=estimates,
        speed_unit=args.speed_unit,
        show_raster_objects=args.show_raster_objects,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
pdb.set_trace()
