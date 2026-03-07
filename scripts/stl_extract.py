
#!/usr/bin/env python3
"""
stl_extract.py

Extract useful information from an STL file, including:
- file format detection (ASCII or binary STL)
- triangle count
- header text (binary STL)
- bounding box
- unique vertex / edge counts
- connected components
- manifold edge check
- surface area
- signed / enclosed volume estimate

Usage:
    python stl_extract.py model.stl
    python stl_extract.py model.stl --json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import pdb


Vec3 = tuple[float, float, float]
Face = tuple[Vec3, Vec3, Vec3]


@dataclass
class STLReport:
    filename: str
    format: str
    file_size_bytes: int
    header_text: str | None
    triangle_count: int
    unique_vertices: int
    unique_edges: int
    connected_components: int
    all_edges_shared_by_two_faces: bool
    bbox_min: Vec3
    bbox_max: Vec3
    size_xyz_mm: Vec3
    size_xyz_in: Vec3
    surface_area_mm2: float
    surface_area_cm2: float
    surface_area_in2: float
    volume_mm3: float
    volume_cm3: float
    volume_in3: float


def vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def triangle_area(v1: Vec3, v2: Vec3, v3: Vec3) -> float:
    ab = vec_sub(v2, v1)
    ac = vec_sub(v3, v1)
    cp = cross(ab, ac)
    return 0.5 * math.sqrt(dot(cp, cp))


def signed_tetra_volume(v1: Vec3, v2: Vec3, v3: Vec3) -> float:
    return dot(v1, cross(v2, v3)) / 6.0


def detect_stl_format(path: Path) -> str:
    size = path.stat().st_size
    if size < 84:
        raise ValueError("File is too small to be a valid STL.")

    with path.open("rb") as f:
        header = f.read(80)
        tri_count_bytes = f.read(4)
        if len(tri_count_bytes) != 4:
            raise ValueError("Could not read STL triangle count.")
        tri_count = struct.unpack("<I", tri_count_bytes)[0]
        expected_binary_size = 84 + tri_count * 50

    if expected_binary_size == size:
        return "binary"

    with path.open("rb") as f:
        start = f.read(512).lstrip()
    if start.lower().startswith(b"solid"):
        return "ascii"

    return "binary"


def parse_binary_stl(path: Path) -> tuple[str, list[Face]]:
    faces: list[Face] = []
    with path.open("rb") as f:
        header = f.read(80)
        header_text = header.decode("ascii", errors="replace").strip("\x00").strip()
        tri_count = struct.unpack("<I", f.read(4))[0]

        for _ in range(tri_count):
            record = f.read(50)
            if len(record) != 50:
                raise ValueError("Unexpected end of file while reading binary STL.")
            vals = struct.unpack("<12fH", record)
            v1 = (vals[3], vals[4], vals[5])
            v2 = (vals[6], vals[7], vals[8])
            v3 = (vals[9], vals[10], vals[11])
            faces.append((v1, v2, v3))

    return header_text, faces


def parse_ascii_stl(path: Path) -> tuple[str | None, list[Face]]:
    faces: list[Face] = []
    header_text: str | None = None
    current_vertices: list[Vec3] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            lower = stripped.lower()

            if lower.startswith("solid") and header_text is None:
                header_text = stripped[5:].strip() or None

            if lower.startswith("vertex"):
                parts = stripped.split()
                if len(parts) < 4:
                    continue
                vertex = (float(parts[1]), float(parts[2]), float(parts[3]))
                current_vertices.append(vertex)
                if len(current_vertices) == 3:
                    faces.append(tuple(current_vertices))  # type: ignore[arg-type]
                    current_vertices = []

    return header_text, faces


def canonical_edge(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def analyze_faces(path: Path, header_text: str | None, file_format: str, faces: list[Face]) -> STLReport:
    if not faces:
        raise ValueError("No triangles found in STL file.")

    vertex_index: dict[Vec3, int] = {}
    vertices: list[Vec3] = []
    indexed_faces: list[tuple[int, int, int]] = []

    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    surface_area = 0.0
    signed_volume = 0.0

    for v1, v2, v3 in faces:
        for v in (v1, v2, v3):
            if v not in vertex_index:
                vertex_index[v] = len(vertices)
                vertices.append(v)
            min_x = min(min_x, v[0])
            min_y = min(min_y, v[1])
            min_z = min(min_z, v[2])
            max_x = max(max_x, v[0])
            max_y = max(max_y, v[1])
            max_z = max(max_z, v[2])

        i1 = vertex_index[v1]
        i2 = vertex_index[v2]
        i3 = vertex_index[v3]
        indexed_faces.append((i1, i2, i3))

        surface_area += triangle_area(v1, v2, v3)
        signed_volume += signed_tetra_volume(v1, v2, v3)

    edge_counts: Counter[tuple[int, int]] = Counter()
    vertex_neighbors: dict[int, set[int]] = defaultdict(set)

    for i1, i2, i3 in indexed_faces:
        edges = (
            canonical_edge(i1, i2),
            canonical_edge(i2, i3),
            canonical_edge(i3, i1),
        )
        for e1, e2 in edges:
            edge_counts[(e1, e2)] += 1
            vertex_neighbors[e1].add(e2)
            vertex_neighbors[e2].add(e1)

    visited: set[int] = set()
    components = 0
    for start in range(len(vertices)):
        if start in visited:
            continue
        components += 1
        queue = deque([start])
        visited.add(start)
        while queue:
            cur = queue.popleft()
            for nxt in vertex_neighbors[cur]:
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)

    size_xyz_mm = (max_x - min_x, max_y - min_y, max_z - min_z)
    size_xyz_in = tuple(v / 25.4 for v in size_xyz_mm)

    area_cm2 = surface_area / 100.0
    area_in2 = surface_area / (25.4 * 25.4)

    volume_mm3 = abs(signed_volume)
    volume_cm3 = volume_mm3 / 1000.0
    volume_in3 = volume_mm3 / (25.4 ** 3)

    return STLReport(
        filename=path.name,
        format=file_format,
        file_size_bytes=path.stat().st_size,
        header_text=header_text,
        triangle_count=len(faces),
        unique_vertices=len(vertices),
        unique_edges=len(edge_counts),
        connected_components=components,
        all_edges_shared_by_two_faces=all(count == 2 for count in edge_counts.values()),
        bbox_min=(min_x, min_y, min_z),
        bbox_max=(max_x, max_y, max_z),
        size_xyz_mm=size_xyz_mm,
        size_xyz_in=size_xyz_in,
        surface_area_mm2=surface_area,
        surface_area_cm2=area_cm2,
        surface_area_in2=area_in2,
        volume_mm3=volume_mm3,
        volume_cm3=volume_cm3,
        volume_in3=volume_in3,
    )


def extract_stl_info(filename: str) -> STLReport:
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    file_format = detect_stl_format(path)
    if file_format == "binary":
        header_text, faces = parse_binary_stl(path)
    else:
        header_text, faces = parse_ascii_stl(path)

    return analyze_faces(path, header_text, file_format, faces)


def format_vec(vec: Iterable[float], places: int = 3) -> str:
    return "(" + ", ".join(f"{v:.{places}f}" for v in vec) + ")"


def report_to_text(report: STLReport) -> str:
    lines = [
        "STL Summary",
        "===========",
        "",
        f"Filename: {report.filename}",
        f"Format: {report.format}",
        f"File size: {report.file_size_bytes:,} bytes",
        f"Header text: {report.header_text or '(none)'}",
        f"Triangle count: {report.triangle_count:,}",
        "",
        "Geometry",
        "--------",
        f"Bounding box min: {format_vec(report.bbox_min)}",
        f"Bounding box max: {format_vec(report.bbox_max)}",
        f"Overall size (mm): {format_vec(report.size_xyz_mm)}",
        f"Overall size (in): {format_vec(report.size_xyz_in)}",
        "",
        "Mesh Quality / Topology",
        "-----------------------",
        f"Unique vertices: {report.unique_vertices:,}",
        f"Unique edges: {report.unique_edges:,}",
        f"Connected components: {report.connected_components:,}",
        f"Every edge shared by exactly 2 faces: {'yes' if report.all_edges_shared_by_two_faces else 'no'}",
        "",
        "Surface Area / Volume",
        "---------------------",
        f"Surface area: {report.surface_area_mm2:.2f} mm^2",
        f"Surface area: {report.surface_area_cm2:.2f} cm^2",
        f"Surface area: {report.surface_area_in2:.2f} in^2",
        f"Volume: {report.volume_mm3:.2f} mm^3",
        f"Volume: {report.volume_cm3:.2f} cm^3",
        f"Volume: {report.volume_in3:.3f} in^3",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract useful information from an STL file.")
    parser.add_argument("filename", help="Path to the STL file")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    args = parser.parse_args()

    report = extract_stl_info(args.filename)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(report_to_text(report))


if __name__ == "__main__":
    main()
    pdb.set_trace()
