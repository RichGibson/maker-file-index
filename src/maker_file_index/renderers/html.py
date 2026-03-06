from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from jinja2 import Environment, PackageLoader, select_autoescape

from maker_file_index.indexer import group_by_directory
from maker_file_index.plugins.lightburn import extract_lightburn_details

LIGHTBURN_EXTS = {"lbrn2", "lbrn"}


def url_path(p: str) -> str:
    """
    Convert a filesystem-relative path to a browser-friendly URL path.
    Encodes spaces and special chars, keeps / separators.
    """
    return quote(p.replace(os.sep, "/"), safe="/")

def _fmt_time() -> str:
    return (
        datetime.now()
        .astimezone()
        .strftime("%B %d, %Y %I:%M %p")
        .lstrip("0")
        .replace("AM", "am")
        .replace("PM", "pm")
    )


EXT_TO_LABEL = {
    "lbrn2": "LightBurn",
    "lbrn":  "LightBurn",
    "stl":   "STL",
    "scad":  "OpenSCAD",
    "3mf":   "3MF",
    "svg":   "SVG",
    "dxf":   "DXF",
}


def _exts_to_labels(exts: list[str]) -> str:
    """Return space-separated unique lowercase labels for a list of extensions."""
    seen = []
    for ext in exts:
        label = EXT_TO_LABEL.get(ext, ext.upper()).lower()
        if label not in seen:
            seen.append(label)
    return " ".join(seen)


def _format_ext_counts(ext_counts: dict) -> str:
    if not ext_counts:
        return ""
    items = sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{n} {ext}" for ext, n in items]
    return f"({', '.join(parts)})"

def build_tree(
    base: Path,
    dirs: set[Path],
    *,
    page_path_for_dir,
    current_page_dir: Path,
    current_dir: Path | None = None,
) -> list[dict]:
    """
    Build a nested directory tree starting at base.
    Each node includes a link to that directory's index.html relative to current_page_dir.
    Nodes matching current_dir are marked with is_current=True.
    """
    children = [d for d in dirs if d.parent == base and d != base]
    children = sorted(children, key=lambda x: x.name.lower())

    nodes: list[dict] = []
    for c in children:
        link = os.path.relpath(page_path_for_dir(c), start=current_page_dir)
        nodes.append(
            {
                "name": c.name,
                "link": link,
                "is_current": c == current_dir,
                "children": build_tree(
                    c,
                    dirs,
                    page_path_for_dir=page_path_for_dir,
                    current_page_dir=current_page_dir,
                    current_dir=current_dir,
                ),
            }
        )

    return nodes

def write_landing_page_html(records, out_dir: Path, root_dir: Path) -> None:
    """
    Writes a top-level index.html landing page at out_dir/index.html
    showing all top-level directories with summary stats.
    """
    out_dir = out_dir.expanduser().resolve()
    root_dir = root_dir.expanduser().resolve()

    env = Environment(
        loader=PackageLoader("maker_file_index", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
    template = env.get_template("landing.html.j2")

    grouped = group_by_directory(records)

    # Top-level dirs only (immediate children of root_dir), newest first
    def _dir_mtime(d: Path) -> float:
        recs = grouped[d].get("records", [])
        mtimes = []
        for r in recs:
            try:
                mtimes.append(r.path.stat().st_mtime)
            except OSError:
                pass
        return max(mtimes) if mtimes else 0.0

    top_dirs = sorted(
        [d for d in grouped if d.parent == root_dir],
        key=_dir_mtime,
        reverse=True,
    )

    dirs_root = out_dir / "dirs"

    def page_path_for_dir(d: Path) -> Path:
        rel = d.relative_to(root_dir)
        return (dirs_root / rel / "index.html").resolve()

    dir_cards = []
    for d in top_dirs:
        bucket = grouped[d]
        child_page = page_path_for_dir(d)
        link = os.path.relpath(child_page, start=out_dir)

        first_thumb = ""
        for r in bucket.get("records", []):
            if r.thumbnail_path and Path(r.thumbnail_path).exists():
                first_thumb = url_path(os.path.relpath(r.thumbnail_path, start=out_dir))
                break

        dir_exts = list(bucket.get("ext_counts", {}).keys())
        dir_cards.append({
            "name": d.name,
            "link": link,
            "first_thumb": first_thumb,
            "counts": _format_ext_counts(bucket.get("ext_counts", {})),
            "labels": _exts_to_labels(dir_exts),
        })

    # Summary stats
    total_files = len(records)
    total_dirs = len(grouped)
    all_ext_counts: dict[str, int] = {}
    for bucket in grouped.values():
        for ext, n in bucket.get("ext_counts", {}).items():
            all_ext_counts[ext] = all_ext_counts.get(ext, 0) + n

    # Merge per-ext counts into per-label counts (e.g. lbrn + lbrn2 → LightBurn)
    label_counts: dict[str, int] = {}
    for ext, count in all_ext_counts.items():
        label = EXT_TO_LABEL.get(ext, ext.upper())
        label_counts[label] = label_counts.get(label, 0) + count
    type_stats = sorted(
        [{"label": label, "key": label.lower(), "count": count}
         for label, count in label_counts.items()],
        key=lambda x: -x["count"],
    )

    # All files for cross-directory search
    all_files = []
    for d, bucket in grouped.items():
        # Find the top-level parent dir for linking
        cur = d
        while cur.parent != root_dir and cur.parent != cur:
            cur = cur.parent
        dir_page = page_path_for_dir(d) if d != root_dir else page_path_for_dir(d)
        dir_link = os.path.relpath(dir_page, start=out_dir)

        for r in sorted(bucket.get("records", []), key=lambda r: r.path.name.lower()):
            ext = r.path.suffix.lower().lstrip(".")

            # Detail page link for LightBurn files, raw file otherwise
            if ext in LIGHTBURN_EXTS:
                rel = r.path.parent.relative_to(root_dir)
                detail_page = (dirs_root / rel / r.path.stem).with_suffix(".html")
                file_link = url_path(os.path.relpath(detail_page, start=out_dir))
            else:
                file_link = url_path(os.path.relpath(r.path, start=out_dir))

            thumb = ""
            tp = r.thumbnail_path
            if tp:
                tp = Path(tp)
                if str(tp) not in ("", ".", "./"):
                    if not tp.is_absolute():
                        tp = (r.path.parent / tp).resolve()
                    if tp.exists() and tp.is_file():
                        thumb = url_path(os.path.relpath(tp, start=out_dir))

            all_files.append({
                "name": r.path.name,
                "ext": ext,
                "link": file_link,
                "thumb": thumb,
                "dir_name": d.name,
                "dir_link": dir_link,
            })

    rendered = template.render(
        generated_at=_fmt_time(),
        total_files=total_files,
        total_dirs=total_dirs,
        type_stats=type_stats,
        dirs=dir_cards,
        all_files_json=json.dumps(all_files),
    )

    landing_path = out_dir / "index.html"
    landing_path.write_text(rendered, encoding="utf-8")


def write_directory_pages_html(records, out_dir: Path, root_dir: Path) -> None:
    """
    Writes one HTML page per directory under:
      out_dir / "dirs" / <relative_dir> / "index.html"
    """
    out_dir = out_dir.expanduser().resolve()
    root_dir = root_dir.expanduser().resolve()
    dirs_root = out_dir / "dirs"
    dirs_root.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=PackageLoader("maker_file_index", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
    template = env.get_template("dir_index.html.j2")
    generated_at = _fmt_time()

    grouped = group_by_directory(records)

    # all dirs we know about (plus ancestors up to root)
    all_dirs = set(grouped.keys())
    for d in list(all_dirs):
        cur = d
        while True:
            all_dirs.add(cur)
            if cur == root_dir:
                break
            if cur.parent == cur:
                break
            cur = cur.parent

    all_dirs = sorted(all_dirs, key=lambda x: str(x).lower())

    def page_path_for_dir(d: Path) -> Path:
        rel = d.relative_to(root_dir) if d != root_dir else Path(".")
        return (dirs_root / rel / "index.html").resolve()

    for d in all_dirs:
        page_path = page_path_for_dir(d)
        page_path.parent.mkdir(parents=True, exist_ok=True)

        # Subdirectories cards
        subdirs = []
        for child in all_dirs:
            if child.parent == d and child != d:
                child_page = page_path_for_dir(child)
                link = os.path.relpath(child_page, start=page_path.parent)

                # README discovery
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
                    readme_title = lines[0].strip() if lines else ""
                    readme_link = url_path(os.path.relpath(readme_path, start=page_path.parent))

                # First thumbnail in that directory (from any record there)
                first_thumb = ""
                child_bucket = grouped.get(child, {})
                child_recs = child_bucket.get("records", [])
                for r in child_recs:
                    if r.thumbnail_path and Path(r.thumbnail_path).exists():
                        first_thumb = url_path(os.path.relpath(r.thumbnail_path, start=page_path.parent))
                        break

                child_ext_counts = child_bucket.get("ext_counts", {})
                counts = _format_ext_counts(child_ext_counts)
                child_exts = list(child_ext_counts.keys())

                subdirs.append(
                    {
                        "name": child.name,
                        "link": link,
                        "readme_title": readme_title,
                        "readme_link": readme_link,
                        "first_thumb": first_thumb,
                        "counts": counts,
                        "labels": _exts_to_labels(child_exts),
                    }
                )

        # File cards for this directory
        bucket = grouped.get(d, {})
        recs = bucket.get("records", [])
        recs = sorted(recs, key=lambda r: r.path.name.lower())

        file_cards = []
        for r in recs:
            thumb = ""
            tp = r.thumbnail_path

            if tp:
                tp = Path(tp)

                # IMPORTANT: ignore sentinel empty thumbnail paths
                if str(tp) in ("", ".", "./"):
                    tp = None

            if tp:
                if not tp.is_absolute():
                    tp = (r.path.parent / tp).resolve()

                if tp.exists() and tp.is_file():
                    thumb = url_path(os.path.relpath(tp, start=page_path.parent))


            # display: first line of notes, else filename
            display = r.path.name
            if r.notes:
                first_line = r.notes.splitlines()[0].strip()
                if first_line:
                    display = first_line

            notes_snippet = ""
            if r.notes:
                lines = [l.strip() for l in r.notes.splitlines() if l.strip()]
                if len(lines) > 1:
                    notes_snippet = " ".join(lines[1:])[:120]

            ext = r.path.suffix.lower().lstrip(".")

            # For LightBurn files, link to a detail page instead of the raw file
            detail_link = ""
            if ext in LIGHTBURN_EXTS:
                rel = r.path.parent.relative_to(root_dir)
                detail_page = (dirs_root / rel / r.path.stem).with_suffix(".html")
                detail_link = url_path(os.path.relpath(detail_page, start=page_path.parent))

            file_cards.append(
                {
                    "path": url_path(os.path.relpath(r.path, start=page_path.parent)),
                    "detail_link": detail_link,
                    "thumb": thumb,
                    "display": display,
                    "ext": ext,
                    "labels": _exts_to_labels([ext]),
                    "notes": notes_snippet,
                    "error": r.error or "",
                }
            )

        show_tree= True
        tree_data=[]
        if show_tree:
            tree_data = build_tree(
                    root_dir,
                    set(all_dirs),
                    page_path_for_dir=page_path_for_dir,
                    current_page_dir=page_path.parent,
                    current_dir=d,
            )

        home_link = os.path.relpath(out_dir / "index.html", start=page_path.parent)

        # Breadcrumbs: root → ... → d
        crumb_parts = []
        cur = d
        while True:
            crumb_parts.append(cur)
            if cur == root_dir or cur.parent == cur:
                break
            cur = cur.parent
        crumb_parts.reverse()
        breadcrumbs = []
        for part in crumb_parts:
            part_page = page_path_for_dir(part)
            breadcrumbs.append({
                "name": part.name,
                "link": os.path.relpath(part_page, start=page_path.parent),
                "is_current": part == d,
            })

        # Unique type labels present on this page (files + subdirs)
        seen_labels: dict[str, str] = {}
        for fc in file_cards:
            label = EXT_TO_LABEL.get(fc["ext"], fc["ext"].upper())
            seen_labels[label.lower()] = label
        for sd in subdirs:
            for lbl in sd["labels"].split():
                display = EXT_TO_LABEL.get(lbl, lbl.upper())
                seen_labels[lbl] = display
        page_types = sorted(
            [{"label": display, "key": key} for key, display in seen_labels.items()],
            key=lambda x: x["label"],
        )

        rendered = template.render(
            directory=str(d),
            directory_name=str(d.name),
            generated_at=generated_at,
            subdirs=subdirs,
            file_cards=file_cards,
            tree_data=tree_data,
            show_tree=show_tree,
            home_link=home_link,
            breadcrumbs=breadcrumbs,
            page_types=page_types,
        )

        page_path.write_text(rendered, encoding="utf-8")


def write_lightburn_detail_pages_html(records, out_dir: Path, root_dir: Path) -> None:
    """
    For each LightBurn record, writes a detail page at:
      out_dir/dirs/<relative_dir>/<stem>.html
    """
    out_dir = out_dir.expanduser().resolve()
    root_dir = root_dir.expanduser().resolve()
    dirs_root = out_dir / "dirs"

    env = Environment(
        loader=PackageLoader("maker_file_index", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
    template = env.get_template("lightburn_detail.html.j2")

    lb_records = [r for r in records if r.path.suffix.lower().lstrip(".") in LIGHTBURN_EXTS]

    for r in lb_records:
        rel = r.path.parent.relative_to(root_dir)
        page_path = (dirs_root / rel / r.path.stem).with_suffix(".html")
        page_path.parent.mkdir(parents=True, exist_ok=True)

        details = extract_lightburn_details(r.path)

        # Thumbnail relative to this page
        thumbnail = ""
        tp = r.thumbnail_path
        if tp:
            tp = Path(tp)
            if str(tp) not in ("", ".", "./"):
                if not tp.is_absolute():
                    tp = (r.path.parent / tp).resolve()
                if tp.exists() and tp.is_file():
                    thumbnail = url_path(os.path.relpath(tp, start=page_path.parent))

        # File stats
        try:
            stat = r.path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size_bytes = stat.st_size
            if size_bytes >= 1024 * 1024:
                file_size = f"{size_bytes / 1024 / 1024:.1f} MB"
            elif size_bytes >= 1024:
                file_size = f"{size_bytes / 1024:.1f} KB"
            else:
                file_size = f"{size_bytes} B"
        except OSError:
            modified = ""
            file_size = ""

        # Home link
        home_link = os.path.relpath(out_dir / "index.html", start=page_path.parent)

        # Breadcrumbs: root → ... → dir → filename
        crumb_parts = []
        cur = r.path.parent
        while True:
            crumb_parts.append(cur)
            if cur == root_dir or cur.parent == cur:
                break
            cur = cur.parent
        crumb_parts.reverse()

        breadcrumbs = []
        for part in crumb_parts:
            part_rel = part.relative_to(root_dir) if part != root_dir else Path(".")
            part_page = (dirs_root / part_rel / "index.html").resolve()
            breadcrumbs.append({
                "name": part.name,
                "link": os.path.relpath(part_page, start=page_path.parent),
            })
        # Add the file itself as the last crumb (no link — shown as filename in template)
        breadcrumbs.append({"name": r.path.name, "link": ""})

        rendered = template.render(
            filename=r.path.name,
            home_link=home_link,
            breadcrumbs=breadcrumbs,
            thumbnail=thumbnail,
            details=details,
            modified=modified,
            file_size=file_size,
        )

        page_path.write_text(rendered, encoding="utf-8")
