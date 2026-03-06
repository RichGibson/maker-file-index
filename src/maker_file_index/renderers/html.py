from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from jinja2 import Environment, PackageLoader, select_autoescape

from maker_file_index.indexer import group_by_directory


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

    # Top-level dirs only (immediate children of root_dir)
    top_dirs = sorted(
        [d for d in grouped if d.parent == root_dir],
        key=lambda d: d.name.lower(),
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

        dir_cards.append({
            "name": d.name,
            "link": link,
            "first_thumb": first_thumb,
            "counts": _format_ext_counts(bucket.get("ext_counts", {})),
        })

    # Summary stats
    total_files = len(records)
    total_dirs = len(grouped)
    all_ext_counts: dict[str, int] = {}
    for bucket in grouped.values():
        for ext, n in bucket.get("ext_counts", {}).items():
            all_ext_counts[ext] = all_ext_counts.get(ext, 0) + n
    ext_counts = sorted(all_ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))

    rendered = template.render(
        generated_at=_fmt_time(),
        total_files=total_files,
        total_dirs=total_dirs,
        ext_counts=ext_counts,
        dirs=dir_cards,
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

                counts = _format_ext_counts(child_bucket.get("ext_counts", {}))

                subdirs.append(
                    {
                        "name": child.name,
                        "link": link,
                        "readme_title": readme_title,
                        "readme_link": readme_link,
                        "first_thumb": first_thumb,
                        "counts": counts,
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

            file_cards.append(
                {
                    "path": url_path(os.path.relpath(r.path, start=page_path.parent)),
                    "thumb": thumb,
                    "display": display,
                    "ext": r.path.suffix.lower().lstrip("."),
                    "notes": notes_snippet,
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

        home_link = os.path.relpath(page_path_for_dir(root_dir), start=page_path.parent)

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
        )

        page_path.write_text(rendered, encoding="utf-8")
