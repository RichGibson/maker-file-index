from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from maker_file_index.indexer import group_by_directory


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
) -> list[dict]:
    """
    Build a nested directory tree starting at base.
    Each node includes a link to that directory's index.html relative to current_page_dir.
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
                "children": build_tree(
                    c,
                    dirs,
                    page_path_for_dir=page_path_for_dir,
                    current_page_dir=current_page_dir,
                ),
            }
        )

    return nodes

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
                    readme_link = os.path.relpath(readme_path, start=page_path.parent)

                # First thumbnail in that directory (from any record there)
                first_thumb = ""
                child_bucket = grouped.get(child, {})
                child_recs = child_bucket.get("records", [])
                for r in child_recs:
                    if r.thumbnail_path and Path(r.thumbnail_path).exists():
                        first_thumb = os.path.relpath(r.thumbnail_path, start=page_path.parent)
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
            if r.thumbnail_path and Path(r.thumbnail_path).exists():
                thumb = os.path.relpath(r.thumbnail_path, start=page_path.parent)

            # display: first line of notes, else filename
            display = r.path.name
            if r.notes:
                first_line = r.notes.splitlines()[0].strip()
                if first_line:
                    display = first_line

            file_cards.append(
                {
                    "path": os.path.relpath(r.path, start=page_path.parent),
                    "thumb": thumb,
                    "display": display,
                    "ext": r.path.suffix.lower().lstrip("."),
                }
            )

        show_tree= (d != root_dir) 
        tree_data=[]
        if show_tree:
            tree_data = build_tree(
                    d,
                    set(all_dirs),
                    page_path_for_dir=page_path_for_dir,
                    current_page_dir=page_path.parent,
            )

        rendered = template.render(
            directory=str(d),
            generated_at=generated_at,
            subdirs=subdirs,
            file_cards=file_cards,
            tree_data=tree_data,
            show_tree=show_tree
        )

        page_path.write_text(rendered, encoding="utf-8")
