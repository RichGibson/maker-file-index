from __future__ import annotations

import os
from collections import defaultdict


def _relpath(path, start=os.curdir) -> str:
    """os.path.relpath with forward slashes (Windows-safe for markdown links)."""
    return os.path.relpath(path, start=start).replace(os.sep, "/")
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from maker_file_index.indexer import group_by_directory
from maker_file_index.model import IndexRecord
from maker_file_index.plugins.dxf import extract_dxf_details
from maker_file_index.plugins.lightburn import extract_lightburn_details
from maker_file_index.plugins.cdr import extract_cdr_details
from maker_file_index.plugins.scad import extract_scad_details
from maker_file_index.plugins.stl import extract_stl_details
from maker_file_index.plugins.svg import extract_svg_details
from maker_file_index.plugins.three_mf import extract_3mf_details

LIGHTBURN_EXTS = {"lbrn2", "lbrn"}
STL_EXTS = {"stl"}
THREE_MF_EXTS = {"3mf"}
SVG_EXTS = {"svg"}
DXF_EXTS = {"dxf"}
SCAD_EXTS = {"scad"}
CDR_EXTS = {"cdr"}
DETAIL_EXTS = LIGHTBURN_EXTS | STL_EXTS | THREE_MF_EXTS | SVG_EXTS | DXF_EXTS | SCAD_EXTS | CDR_EXTS

_DETAIL_CONFIG: dict[str, tuple[str, object]] = {
    **{ext: ("lightburn_detail.md.j2", extract_lightburn_details) for ext in LIGHTBURN_EXTS},
    **{ext: ("stl_detail.md.j2", extract_stl_details) for ext in STL_EXTS},
    **{ext: ("three_mf_detail.md.j2", extract_3mf_details) for ext in THREE_MF_EXTS},
    **{ext: ("svg_detail.md.j2", extract_svg_details) for ext in SVG_EXTS},
    **{ext: ("dxf_detail.md.j2", extract_dxf_details) for ext in DXF_EXTS},
    **{ext: ("scad_detail.md.j2", extract_scad_details) for ext in SCAD_EXTS},
    **{ext: ("cdr_detail.md.j2", extract_cdr_details) for ext in CDR_EXTS},
}


def _fmt_now() -> str:
    return (
        datetime.now()
        .astimezone()
        .strftime("%B %d, %Y %I:%M %p")
        .lstrip("0")
        .replace("AM", "am")
        .replace("PM", "pm")
    )


def _fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def _make_env() -> Environment:
    return Environment(
        loader=PackageLoader("maker_file_index", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )


def write_markdown_report(
    records,
    output_path: Path,
    root_for_rel: Path | None = None,
    root_dir: Path | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = _make_env()
    template = env.get_template("report.md.j2")
    generated_at = _fmt_now()

    # File type counts
    ext_counts: dict[str, int] = {}
    for r in records:
        ext = r.path.suffix.lower().lstrip(".") or "other"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    ext_counts = dict(sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0])))

    # Top-level directories
    top_dirs = []
    if root_dir is not None:
        root_dir_p = Path(root_dir).expanduser().resolve()
        grouped = group_by_directory(records)
        dirs_root = output_path.parent / "dirs"

        seen: set[Path] = set()
        for d in grouped:
            cur = d
            while cur != root_dir_p and cur.parent != cur:
                if cur.parent == root_dir_p:
                    seen.add(cur)
                    break
                cur = cur.parent

        for d in sorted(seen, key=lambda x: x.name.lower()):
            dir_page = dirs_root / d.relative_to(root_dir_p) / "index.md"
            link = _relpath(dir_page, start=output_path.parent)
            ext_c = grouped.get(d, {}).get("ext_counts", {})
            count_str = ", ".join(
                f"{n} {ext}" for ext, n in sorted(ext_c.items(), key=lambda kv: (-kv[1], kv[0]))
            )
            top_dirs.append({"name": d.name, "link": link, "counts": count_str})

    rendered = template.render(
        records=records,
        generated_at=generated_at,
        ext_counts=ext_counts,
        total_files=len(records),
        total_dirs=len(set(r.directory for r in records)),
        top_dirs=top_dirs,
    )
    output_path.write_text(rendered, encoding="utf-8")


def write_directory_pages(records, out_dir: Path, root_dir: Path) -> None:
    """
    Writes one Markdown page per directory under:
      out_dir / "dirs" / <relative_dir> / "index.md"
    """
    out_dir = out_dir.expanduser().resolve()
    root_dir = root_dir.expanduser().resolve()
    dirs_root = out_dir / "dirs"
    dirs_root.mkdir(parents=True, exist_ok=True)

    env = _make_env()
    template = env.get_template("dir_index.md.j2")
    generated_at = _fmt_now()

    grouped = group_by_directory(records)

    # All dirs including ancestors up to root
    all_dirs: set[Path] = set(grouped.keys())
    for d in list(all_dirs):
        cur = d
        while True:
            all_dirs.add(cur)
            if cur == root_dir or cur.parent == cur:
                break
            cur = cur.parent

    all_dirs_sorted = sorted(all_dirs, key=lambda x: str(x).lower())

    def page_path_for_dir(d: Path) -> Path:
        rel = d.relative_to(root_dir) if d != root_dir else Path(".")
        return (dirs_root / rel / "index.md").resolve()

    def format_ext_counts(ext_counts: dict) -> str:
        if not ext_counts:
            return ""
        items = sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ", ".join(f"{n} {ext}" for ext, n in items)

    for d in all_dirs_sorted:
        page_path = page_path_for_dir(d)
        page_path.parent.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        subdirs = []
        for child in all_dirs_sorted:
            if child.parent == d and child != d:
                child_page = page_path_for_dir(child)
                link = _relpath(child_page, start=page_path.parent)

                readme_path = None
                for cand in ("README.md", "README.txt"):
                    p = child / cand
                    if p.exists() and p.is_file():
                        readme_path = p
                        break

                readme_title = ""
                readme_link = ""
                if readme_path is not None:
                    lines = readme_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    readme_title = lines[0].lstrip("#").strip() if lines else ""
                    readme_link = _relpath(readme_path, start=page_path.parent)

                child_counts = grouped.get(child, {}).get("ext_counts", {})
                subdirs.append({
                    "name": child.name,
                    "link": str(link),
                    "counts": format_ext_counts(child_counts),
                    "readme_title": readme_title,
                    "readme_link": readme_link,
                })

        # File entries enriched with detail links
        recs = grouped.get(d, {}).get("records", [])
        by_ext: dict[str, list[dict]] = defaultdict(list)
        for r in sorted(recs, key=lambda r: r.path.name.lower()):
            ext = r.path.suffix.lower().lstrip(".") or "<no-ext>"

            detail_link = ""
            if ext in DETAIL_EXTS:
                detail_page = (dirs_root / r.path.parent.relative_to(root_dir) / r.path.stem).with_suffix(".md")
                detail_link = _relpath(detail_page, start=page_path.parent)

            notes_snippet = ""
            if r.notes:
                lines = [ln.strip() for ln in r.notes.splitlines() if ln.strip()]
                notes_snippet = lines[0][:100] if lines else ""

            by_ext[ext].append({
                "name": r.path.name,
                "detail_link": detail_link,
                "notes": notes_snippet,
                "error": r.error or "",
            })

        # Sort ext buckets by descending count
        by_ext = dict(sorted(by_ext.items(), key=lambda kv: (-len(kv[1]), kv[0])))

        # README for this directory
        readme_content = ""
        for cand in ("README.md", "README.txt"):
            rp = d / cand
            if rp.exists() and rp.is_file():
                raw = rp.read_text(encoding="utf-8", errors="replace")
                lines = raw.splitlines()
                body = "\n".join(lines[1:]).strip() if lines else ""
                readme_content = body
                break

        # Breadcrumbs (exclude root itself; stop before adding current dir)
        crumb_parts = []
        cur = d
        while cur != root_dir and cur.parent != cur:
            crumb_parts.append(cur)
            cur = cur.parent
        crumb_parts.reverse()

        breadcrumbs = []
        for part in crumb_parts[:-1]:  # all but the last (current dir)
            part_page = page_path_for_dir(part)
            breadcrumbs.append({
                "name": part.name,
                "link": _relpath(part_page, start=page_path.parent),
            })

        rendered = template.render(
            directory=str(d),
            directory_name=d.name if d != root_dir else d.name,
            generated_at=generated_at,
            subdirs=subdirs,
            by_ext=by_ext,
            readme_content=readme_content,
            breadcrumbs=breadcrumbs,
        )
        page_path.write_text(rendered, encoding="utf-8")


def write_detail_pages_markdown(records, out_dir: Path, root_dir: Path) -> None:
    """
    Writes one Markdown detail page per supported file type record under:
      out_dir / "dirs" / <relative_dir> / <stem>.md
    """
    out_dir = out_dir.expanduser().resolve()
    root_dir = root_dir.expanduser().resolve()
    dirs_root = out_dir / "dirs"

    env = _make_env()
    generated_at = _fmt_now()

    detail_records = [
        r for r in records
        if r.path.suffix.lower().lstrip(".") in DETAIL_EXTS
    ]

    for i, r in enumerate(detail_records, 1):
        ext = r.path.suffix.lower().lstrip(".")
        template_name, extract_fn = _DETAIL_CONFIG[ext]

        rel = r.path.parent.relative_to(root_dir)
        page_path = (dirs_root / rel / r.path.stem).with_suffix(".md")
        page_path.parent.mkdir(parents=True, exist_ok=True)

        # Freshness check
        if page_path.exists() and page_path.stat().st_mtime >= r.path.stat().st_mtime:
            continue
        print(f"  [{i}/{len(detail_records)}] {r.path.name}")

        details = extract_fn(r.path)

        # Thumbnail path relative to this page
        thumbnail = ""
        tp = r.thumbnail_path
        if tp:
            tp = Path(tp)
            if str(tp) not in ("", ".", "./"):
                if not tp.is_absolute():
                    tp = (r.path.parent / tp).resolve()
                if tp.exists() and tp.is_file():
                    thumbnail = _relpath(tp, start=page_path.parent)

        # File stats
        try:
            stat = r.path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            file_size = _fmt_size(stat.st_size)
        except OSError:
            modified = ""
            file_size = ""

        # Breadcrumbs
        crumb_parts = []
        cur = r.path.parent
        while cur != root_dir and cur.parent != cur:
            crumb_parts.append(cur)
            cur = cur.parent
        crumb_parts.reverse()

        breadcrumbs = []
        for part in crumb_parts:
            part_rel = part.relative_to(root_dir)
            part_page = (dirs_root / part_rel / "index.md").resolve()
            breadcrumbs.append({
                "name": part.name,
                "link": _relpath(part_page, start=page_path.parent),
            })
        breadcrumbs.append({"name": r.path.name, "link": ""})

        template = env.get_template(template_name)
        rendered = template.render(
            filename=r.path.name,
            breadcrumbs=breadcrumbs,
            thumbnail=thumbnail,
            details=details,
            modified=modified,
            file_size=file_size,
            generated_at=generated_at,
        )
        page_path.write_text(rendered, encoding="utf-8")
