from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh


# ---------------------------------------------------------------------------
# SCAD detail extraction (ported from scripts/scad_extract.py)
# ---------------------------------------------------------------------------

_ASSIGNMENT_RE = re.compile(
    r'^\s*([A-Za-z_]\w*)\s*=\s*([^;]+);(?:\s*//\s*(.*))?\s*$',
    re.MULTILINE,
)
_MODULE_RE = re.compile(
    r'^\s*module\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{',
    re.MULTILINE,
)
_CALL_RE = re.compile(r'(?<!module\s)\b([A-Za-z_]\w*)\s*\(')
_INCLUDE_RE = re.compile(r'^\s*(include|use)\s*<([^>]+)>\s*;?', re.MULTILINE)
_STRING_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
_LINE_COMMENT_RE = re.compile(r'//(.*)$', re.MULTILINE)
_BLOCK_COMMENT_RE = re.compile(r'/\*(.*?)\*/', re.DOTALL)

_PRIMITIVES = {"cube","sphere","cylinder","polyhedron","polygon","circle","square","text","surface","import"}
_TRANSFORMS = {"translate","rotate","scale","resize","mirror","multmatrix","color","offset","minkowski","hull","projection","linear_extrude","rotate_extrude","render"}
_CSG_OPS = {"union","difference","intersection"}


def _safe_number(value: str) -> float | int | None:
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


def extract_scad_details(path: Path) -> dict[str, Any]:
    """Extract metadata and structure from an OpenSCAD (.scad) file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        text_no_comments = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        text_no_comments = re.sub(r'//.*$', '', text_no_comments, flags=re.MULTILINE)

        line_comments = [m.strip() for m in _LINE_COMMENT_RE.findall(text) if m.strip()]
        block_comments = [m.strip() for m in _BLOCK_COMMENT_RE.findall(text) if m.strip()]
        strings = _STRING_RE.findall(text)

        assignments: list[dict] = []
        for match in _ASSIGNMENT_RE.finditer(text):
            name, value, trailing_comment = match.groups()
            assignments.append({
                "name": name,
                "value": value.strip(),
                "numeric_value": _safe_number(value.strip()),
                "comment": trailing_comment.strip() if trailing_comment else "",
            })

        modules = []
        for match in _MODULE_RE.finditer(text):
            name, params = match.groups()
            param_list = [p.strip() for p in params.split(",") if p.strip()]
            modules.append({"name": name, "parameters": param_list})

        calls: Counter = Counter()
        for name in _CALL_RE.findall(text_no_comments):
            calls[name] += 1

        module_names = {m["name"] for m in modules}
        primitive_counts = {n: calls[n] for n in sorted(_PRIMITIVES) if calls.get(n, 0)}
        transform_counts = {n: calls[n] for n in sorted(_TRANSFORMS) if calls.get(n, 0)}
        csg_counts = {n: calls[n] for n in sorted(_CSG_OPS) if calls.get(n, 0)}
        custom_module_calls = {n: c for n, c in sorted(calls.items()) if n in module_names}

        includes = [{"kind": kind, "target": target} for kind, target in _INCLUDE_RE.findall(text)]

        return {
            "line_count": text.count("\n") + 1,
            "character_count": len(text),
            "assignments": assignments,
            "modules": modules,
            "includes": includes,
            "primitive_counts": primitive_counts,
            "transform_counts": transform_counts,
            "csg_counts": csg_counts,
            "custom_module_calls": custom_module_calls,
            "comments": (line_comments + block_comments)[:50],
            "strings": strings[:50],
            "error": "",
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def render_scad_thumbnail(scad_path: Path, thumb_path: Path) -> str:
    """
    Render a SCAD file to a PNG thumbnail using the OpenSCAD CLI.
    Returns an error string on failure, or "" on success.
    """
    openscad = shutil.which("openscad")
    if not openscad:
        return "openscad not found in PATH"

    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                openscad,
                "--export-format", "png",
                "--autocenter",
                "--viewall",
                "-o", str(thumb_path),
                str(scad_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return result.stderr.strip() or f"openscad exited with code {result.returncode}"
        if not thumb_path.exists():
            return "openscad ran but produced no output file"
        return ""
    except subprocess.TimeoutExpired:
        return "openscad timed out after 60s"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


class SCADPlugin:
    name = "scad"

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".scad"

    def index(self, path: Path) -> IndexRecord:
        thumb_root = getattr(self, "thumb_root", None)
        scan_root = getattr(self, "scan_root", None)
        thumb_path = thumbnail_path_for(path, thumb_root=thumb_root, scan_root=scan_root)
        error = ""
        if not thumbnail_is_fresh(path, thumb_path):
            rel = path.relative_to(scan_root) if scan_root else Path(path.parent.name) / path.name
            print(f"Creating thumbnail for {rel}")
            error = render_scad_thumbnail(path, thumb_path)

        return IndexRecord(
            path=path,
            directory=path.parent,
            notes="",
            thumbnail_path=thumb_path.resolve() if thumb_path.exists() else Path(""),
            error=error,
        )
