#!/usr/bin/env python3
"""
Extract useful information from a 3MF file.

Features:
- Reads package metadata
- Extracts model/object metadata
- Parses mesh geometry
- Applies build transforms
- Computes bounding boxes, dimensions, surface area, volume
- Counts vertices, triangles, unique edges, connected components
- Checks whether the mesh looks manifold
- Extracts a useful subset of slicer settings when present
- Can emit plain text or JSON

Usage:
    python 3mf_extract.py model.3mf
    python 3mf_extract.py model.3mf --json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import pathlib
import pdb
import sys
import xml.etree.ElementTree as ET
import zipfile


NS = {
    "m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02",
    "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06",
    "b": "http://schemas.bambulab.com/package/2021",
}

USEFUL_PROJECT_KEYS = [
    "printer_model",
    "printer_variant",
    "printer_technology",
    "printable_area",
    "bed_type",
    "nozzle_diameter",
    "filament_type",
    "filament_diameter",
    "layer_height",
    "initial_layer_print_height",
    "sparse_infill_density",
    "sparse_infill_pattern",
    "wall_loops",
    "top_shell_layers",
    "bottom_shell_layers",
    "enable_support",
    "support_type",
    "brim_type",
    "brim_width",
    "outer_wall_speed",
    "inner_wall_speed",
    "initial_layer_speed",
    "travel_speed",
]


def parse_transform(transform_text: str | None) -> list[float]:
    if not transform_text:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    values = [float(x) for x in transform_text.split()]
    if len(values) != 12:
        raise ValueError(f"Expected 12 transform values, got {len(values)}")
    return values


def apply_transform(vertex: tuple[float, float, float], transform: list[float]) -> tuple[float, float, float]:
    a, b, c, d, e, f, g, h, i, j, k, l = transform
    x, y, z = vertex
    return (
        a * x + b * y + c * z + j,
        d * x + e * y + f * z + k,
        g * x + h * y + i * z + l,
    )


def triangle_area_and_signed_volume(
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
) -> tuple[float, float]:
    ax, ay, az = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
    bx, by, bz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
    cx = ay * bz - az * by
    cy = az * bx - ax * bz
    cz = ax * by - ay * bx
    area = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    signed_volume = (
        p1[0] * (p2[1] * p3[2] - p2[2] * p3[1])
        - p1[1] * (p2[0] * p3[2] - p2[2] * p3[0])
        + p1[2] * (p2[0] * p3[1] - p2[1] * p3[0])
    ) / 6.0
    return area, signed_volume


def parse_metadata_entries(root: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in root.findall(".//m:metadata", NS):
        key = entry.attrib.get("name")
        if key:
            result[key] = entry.text or ""
    return result


def parse_model_settings(xml_text: str) -> dict[str, object]:
    root = ET.fromstring(xml_text)
    data: dict[str, object] = {
        "objects": [],
        "plate_metadata": {},
    }

    for obj in root.findall("./object"):
        obj_info: dict[str, object] = {
            "id": obj.attrib.get("id"),
            "metadata": {},
            "parts": [],
        }
        for md in obj.findall("./metadata"):
            obj_info["metadata"][md.attrib.get("key", "")] = md.attrib.get("value", "")
        for part in obj.findall("./part"):
            part_info: dict[str, object] = {
                "id": part.attrib.get("id"),
                "subtype": part.attrib.get("subtype", ""),
                "metadata": {},
                "mesh_stat": {},
            }
            for md in part.findall("./metadata"):
                part_info["metadata"][md.attrib.get("key", "")] = md.attrib.get("value", "")
            mesh_stat = part.find("./mesh_stat")
            if mesh_stat is not None:
                part_info["mesh_stat"] = dict(mesh_stat.attrib)
            obj_info["parts"].append(part_info)
        data["objects"].append(obj_info)

    plate = root.find("./plate")
    if plate is not None:
        for md in plate.findall("./metadata"):
            data["plate_metadata"][md.attrib.get("key", "")] = md.attrib.get("value", "")

    return data


def compute_connectivity(vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]]) -> dict[str, object]:
    parent = list(range(len(vertices)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    edge_counts: collections.Counter[tuple[int, int]] = collections.Counter()
    area = 0.0
    volume = 0.0

    for v1, v2, v3 in triangles:
        p1, p2, p3 = vertices[v1], vertices[v2], vertices[v3]
        tri_area, signed_volume = triangle_area_and_signed_volume(p1, p2, p3)
        area += tri_area
        volume += signed_volume

        edge_counts[tuple(sorted((v1, v2)))] += 1
        edge_counts[tuple(sorted((v2, v3)))] += 1
        edge_counts[tuple(sorted((v3, v1)))] += 1

        union(v1, v2)
        union(v2, v3)

    components = len({find(i) for i in range(len(vertices))})
    edge_share_histogram = collections.Counter(edge_counts.values())
    manifold_like = set(edge_share_histogram.keys()) == {2}

    return {
        "surface_area_mm2": area,
        "volume_mm3": abs(volume),
        "unique_edges": len(edge_counts),
        "connected_components": components,
        "edge_share_histogram": dict(sorted(edge_share_histogram.items())),
        "manifold_like": manifold_like,
    }


def extract_3mf(path: str) -> dict[str, object]:
    result: dict[str, object] = {
        "file": {
            "filename": os.path.basename(path),
            "size_bytes": os.path.getsize(path),
            "format": "3MF",
        }
    }

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        result["package_entries"] = names

        model_path = "3D/3dmodel.model"
        if model_path not in names:
            raise ValueError("3D/3dmodel.model not found in package")

        main_root = ET.fromstring(zf.read(model_path))
        main_meta = parse_metadata_entries(main_root)
        result["package_metadata"] = main_meta
        result["unit"] = main_root.attrib.get("unit", "")
        result["language"] = main_root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "")

        build_item = main_root.find(".//m:build/m:item", NS)
        build_transform = parse_transform(build_item.attrib.get("transform") if build_item is not None else None)
        result["build"] = {
            "objectid": build_item.attrib.get("objectid", "") if build_item is not None else "",
            "printable": build_item.attrib.get("printable", "") if build_item is not None else "",
            "transform": build_transform,
        }

        mesh_model_path = None
        component = main_root.find(".//m:components/m:component", NS)
        if component is not None:
            mesh_model_path = component.attrib.get("{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path")
        if not mesh_model_path:
            mesh_model_path = model_path
        mesh_model_path = mesh_model_path.lstrip("/")

        mesh_root = ET.fromstring(zf.read(mesh_model_path))

        raw_vertices = [
            (float(v.attrib["x"]), float(v.attrib["y"]), float(v.attrib["z"]))
            for v in mesh_root.findall(".//m:vertex", NS)
        ]
        triangles = [
            (int(t.attrib["v1"]), int(t.attrib["v2"]), int(t.attrib["v3"]))
            for t in mesh_root.findall(".//m:triangle", NS)
        ]
        transformed_vertices = [apply_transform(v, build_transform) for v in raw_vertices]

        def bbox(verts: list[tuple[float, float, float]]) -> dict[str, object]:
            mins = [min(v[i] for v in verts) for i in range(3)]
            maxs = [max(v[i] for v in verts) for i in range(3)]
            dims = [maxs[i] - mins[i] for i in range(3)]
            return {
                "min": mins,
                "max": maxs,
                "size": dims,
            }

        raw_bbox = bbox(raw_vertices)
        transformed_bbox = bbox(transformed_vertices)

        geometry = compute_connectivity(transformed_vertices, triangles)
        geometry.update(
            {
                "vertex_count": len(raw_vertices),
                "triangle_count": len(triangles),
                "raw_bbox_mm": raw_bbox,
                "transformed_bbox_mm": transformed_bbox,
            }
        )
        result["geometry"] = geometry

        if "Metadata/project_settings.config" in names:
            project_settings = json.loads(zf.read("Metadata/project_settings.config"))
            result["project_settings_subset"] = {
                key: project_settings[key]
                for key in USEFUL_PROJECT_KEYS
                if key in project_settings
            }

        if "Metadata/model_settings.config" in names:
            result["model_settings"] = parse_model_settings(
                zf.read("Metadata/model_settings.config").decode("utf-8")
            )

        if "Metadata/plate_1.json" in names:
            result["plate_preview"] = json.loads(zf.read("Metadata/plate_1.json"))

    return result


def format_report(data: dict[str, object]) -> str:
    file_info = data["file"]
    geom = data["geometry"]
    package_md = data.get("package_metadata", {})
    project = data.get("project_settings_subset", {})

    raw_bbox = geom["raw_bbox_mm"]
    transformed_bbox = geom["transformed_bbox_mm"]

    lines: list[str] = []
    lines.append(f"Filename: {file_info['filename']}")
    lines.append(f"Format: {file_info['format']}")
    lines.append(f"Size: {file_info['size_bytes']} bytes")
    lines.append(f"Unit: {data.get('unit', '')}")
    lines.append("")

    if package_md:
        lines.append("Package metadata:")
        for key in sorted(package_md):
            lines.append(f"  {key}: {package_md[key]}")
        lines.append("")

    lines.append("Geometry:")
    lines.append(f"  Vertices: {geom['vertex_count']}")
    lines.append(f"  Triangles: {geom['triangle_count']}")
    lines.append(f"  Unique edges: {geom['unique_edges']}")
    lines.append(f"  Connected components: {geom['connected_components']}")
    lines.append(f"  Manifold-like: {geom['manifold_like']}")
    lines.append(f"  Surface area: {geom['surface_area_mm2']:.3f} mm^2")
    lines.append(f"  Volume: {geom['volume_mm3']:.3f} mm^3")
    lines.append("")

    lines.append("Raw mesh bounding box (before build transform):")
    lines.append(
        f"  min={tuple(round(x, 6) for x in raw_bbox['min'])} "
        f"max={tuple(round(x, 6) for x in raw_bbox['max'])} "
        f"size={tuple(round(x, 6) for x in raw_bbox['size'])}"
    )
    lines.append("")

    lines.append("Placed / transformed bounding box:")
    lines.append(
        f"  min={tuple(round(x, 6) for x in transformed_bbox['min'])} "
        f"max={tuple(round(x, 6) for x in transformed_bbox['max'])} "
        f"size={tuple(round(x, 6) for x in transformed_bbox['size'])}"
    )
    lines.append("")
    lines.append(f"Build transform: {data['build']['transform']}")
    lines.append("")

    if project:
        lines.append("Selected slicer settings:")
        for key in sorted(project):
            lines.append(f"  {key}: {project[key]}")
        lines.append("")

    model_settings = data.get("model_settings", {})
    if model_settings:
        lines.append("Model settings summary:")
        for obj in model_settings.get("objects", []):
            lines.append(f"  Object id={obj.get('id')}")
            for key, value in sorted(obj.get("metadata", {}).items()):
                lines.append(f"    {key}: {value}")
            for part in obj.get("parts", []):
                lines.append(f"    Part id={part.get('id')} subtype={part.get('subtype')}")
                for key, value in sorted(part.get("metadata", {}).items()):
                    lines.append(f"      {key}: {value}")
                mesh_stat = part.get("mesh_stat", {})
                if mesh_stat:
                    lines.append(f"      mesh_stat: {mesh_stat}")
        plate_meta = model_settings.get("plate_metadata", {})
        if plate_meta:
            lines.append("  Plate metadata:")
            for key, value in sorted(plate_meta.items()):
                lines.append(f"    {key}: {value}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract useful information from a 3MF file")
    parser.add_argument("filename", help="Path to the 3MF file")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON instead of text")
    args = parser.parse_args()

    data = extract_3mf(args.filename)

    if args.as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(format_report(data))

    pdb.set_trace()
    return 0


if __name__ == "__main__":
    sys.exit(main())
