"""Tests for plugin extract_* functions.

Each test calls the extract function with a real fixture file and asserts that:
  - No error is returned
  - Expected keys are present with sensible types/values
"""
from __future__ import annotations

from pathlib import Path

from maker_file_index.plugins.cdr import extract_cdr_details
from maker_file_index.plugins.dxf import extract_dxf_details
from maker_file_index.plugins.lightburn import extract_lightburn_details
from maker_file_index.plugins.scad import extract_scad_details
from maker_file_index.plugins.stl import extract_stl_details
from maker_file_index.plugins.svg import extract_svg_details
from maker_file_index.plugins.three_mf import extract_3mf_details


# ---------------------------------------------------------------------------
# LightBurn
# ---------------------------------------------------------------------------

def test_lightburn_returns_no_error(lbrn2_file):
    d = extract_lightburn_details(lbrn2_file)
    assert d.get("error", "") == ""


def test_lightburn_has_layers_list(lbrn2_file):
    d = extract_lightburn_details(lbrn2_file)
    assert isinstance(d.get("layers"), list)
    assert len(d["layers"]) > 0


def test_lightburn_layer_has_required_fields(lbrn2_file):
    d = extract_lightburn_details(lbrn2_file)
    layer = d["layers"][0]
    for key in ("index", "name", "type", "speed", "max_power"):
        assert key in layer, f"Missing key '{key}' in layer"


def test_lightburn_has_shape_counts(lbrn2_file):
    d = extract_lightburn_details(lbrn2_file)
    assert isinstance(d.get("shape_counts"), dict)


# ---------------------------------------------------------------------------
# STL
# ---------------------------------------------------------------------------

def test_stl_returns_no_error(stl_file):
    d = extract_stl_details(stl_file)
    assert d.get("error", "") == ""


def test_stl_has_geometry_keys(stl_file):
    d = extract_stl_details(stl_file)
    for key in ("triangle_count", "unique_vertices", "size_x_mm", "size_y_mm", "size_z_mm"):
        assert key in d, f"Missing key '{key}'"


def test_stl_triangle_count_positive(stl_file):
    d = extract_stl_details(stl_file)
    assert int(d["triangle_count"]) > 0


def test_stl_dimensions_are_numeric(stl_file):
    d = extract_stl_details(stl_file)
    assert float(d["size_x_mm"]) >= 0
    assert float(d["size_y_mm"]) >= 0
    assert float(d["size_z_mm"]) >= 0


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def test_svg_returns_no_error(svg_file):
    d = extract_svg_details(svg_file)
    assert d.get("error", "") == ""


def test_svg_has_dimension_keys(svg_file):
    d = extract_svg_details(svg_file)
    for key in ("width", "height", "counts", "path_count"):
        assert key in d, f"Missing key '{key}'"


def test_svg_has_positive_entity_count(svg_file):
    d = extract_svg_details(svg_file)
    assert sum(d["counts"].values()) > 0


# ---------------------------------------------------------------------------
# 3MF
# ---------------------------------------------------------------------------

def test_3mf_returns_no_error(three_mf_file):
    d = extract_3mf_details(three_mf_file)
    assert d.get("error", "") == ""


def test_3mf_has_object_names(three_mf_file):
    d = extract_3mf_details(three_mf_file)
    assert isinstance(d.get("object_names"), list)
    assert len(d["object_names"]) > 0


def test_3mf_has_mesh_data(three_mf_file):
    d = extract_3mf_details(three_mf_file)
    assert "triangle_count" in d
    assert "vertex_count" in d
    assert int(d["triangle_count"]) > 0


# ---------------------------------------------------------------------------
# CDR
# ---------------------------------------------------------------------------

def test_cdr_returns_format_key(cdr_file):
    d = extract_cdr_details(cdr_file)
    assert "format" in d


def test_cdr_format_contains_cdr(cdr_file):
    d = extract_cdr_details(cdr_file)
    assert "CDR" in d["format"]


def test_cdr_has_is_zip_flag(cdr_file):
    d = extract_cdr_details(cdr_file)
    assert "is_zip" in d
    assert isinstance(d["is_zip"], bool)


# ---------------------------------------------------------------------------
# SCAD
# ---------------------------------------------------------------------------

def test_scad_returns_no_error(scad_file):
    d = extract_scad_details(scad_file)
    assert d.get("error", "") == ""


def test_scad_has_line_count(scad_file):
    d = extract_scad_details(scad_file)
    assert d.get("line_count", 0) > 0


def test_scad_finds_modules(scad_file):
    d = extract_scad_details(scad_file)
    names = [m["name"] for m in d.get("modules", [])]
    assert "cylinder_shell" in names


def test_scad_finds_assignments(scad_file):
    d = extract_scad_details(scad_file)
    names = [a["name"] for a in d.get("assignments", [])]
    assert "wall_thickness" in names
    assert "height" in names
    assert "radius" in names


def test_scad_finds_primitives(scad_file):
    d = extract_scad_details(scad_file)
    assert "cylinder" in d.get("primitive_counts", {})


# ---------------------------------------------------------------------------
# DXF
# ---------------------------------------------------------------------------

def test_dxf_returns_no_error(dxf_file):
    d = extract_dxf_details(dxf_file)
    assert d.get("error", "") == ""


def test_dxf_has_entity_keys(dxf_file):
    d = extract_dxf_details(dxf_file)
    for key in ("total_entities", "entity_counts", "layers"):
        assert key in d, f"Missing key '{key}'"


def test_dxf_entity_count_positive(dxf_file):
    d = extract_dxf_details(dxf_file)
    assert d["total_entities"] > 0


def test_dxf_finds_lines_and_circles(dxf_file):
    d = extract_dxf_details(dxf_file)
    counts = d["entity_counts"]
    assert "LINE" in counts
    assert "CIRCLE" in counts
