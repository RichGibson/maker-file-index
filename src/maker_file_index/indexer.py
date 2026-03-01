from __future__ import annotations

import glob
from datetime import datetime
from pathlib import Path
import pdb

from maker_file_index.plugins.loader import load_plugins
from maker_file_index.plugins.base import IndexRecord  # or whatever you named your generic record
from jinja2 import Environment, PackageLoader, select_autoescape
from collections import defaultdict

plugins=load_plugins()

from maker_file_index.plugins.lightburn import (
    LightBurnInfo,
    extract_notes_and_thumbnail,
    is_likely_lightburn_project,
)

def group_by_directory(records):
    grouped = defaultdict(list)
    for r in records:
        grouped[r.directory].append(r)

    print(f"in group by directory")
    return grouped

def write_directory_pages(records, out_dir: Path, root_dir: Path) -> None:
    """
    Writes one page per directory under:
      out_dir / "dirs" / <relative_dir> / "index.md"
    and links subdirectories to their own index pages.
    """
    out_dir = out_dir.expanduser().resolve()
    root_dir = root_dir.expanduser().resolve()
    dirs_root = out_dir / "dirs"
    dirs_root.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=PackageLoader("maker_file_index", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )
    template = env.get_template("dir_index.md.j2")

    generated_at = datetime.now().astimezone().strftime(
        "%B %d, %Y %I:%M %p"
    ).lstrip("0").replace("AM", "am").replace("PM", "pm")

    grouped = group_by_directory(records)

    # Compute page path for every directory we know about (plus ancestors up to root)
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

    def page_path_for_dir(d: Path) -> Path:
        rel = d.relative_to(root_dir) if d != root_dir else Path(".")
        return (dirs_root / rel / "index.md").resolve()

    all_dirs = sorted(all_dirs, key=lambda x: str(x).lower())

    for d in all_dirs:
        page_path = page_path_for_dir(d)
        page_path.parent.mkdir(parents=True, exist_ok=True)

        # Subdirs for this directory (directories directly under d that are in all_dirs)
        subdirs = []
        for child in all_dirs:
            if child.parent == d and child != d:
                child_page = page_path_for_dir(child)
                link = child_page.relative_to(page_path.parent)

                # README discovery (README.md or README.txt)
                readme_path = None
                for cand in ("README.md", "README.txt"):
                    p = child / cand
                    if p.exists() and p.is_file():
                        readme_path = p
                        break

                readme_title = ""
                readme_link = ""
                if readme_path is not None:
                    try:
                        first_line = readme_path.read_text(encoding="utf-8", errors="replace").splitlines()
                        readme_title = first_line[0].strip() if first_line else ""
                    except Exception:
                        readme_title = ""

                    # link to the README file relative to the directory index page
                    readme_link = str(Path("../../../") / readme_path.relative_to(root_dir))

                #pdb.set_trace()

                subdirs.append(
                    {
                        "name": child.name,
                        "link": str(link),
                        "readme_title": readme_title,
                        "readme_link": readme_link,
                    }
                )










        # Records that live directly in this directory
        recs = grouped.get(d, [])
        recs = sorted(recs, key=lambda r: r.path.name.lower())

        rendered = template.render(
            directory=str(d),
            generated_at=generated_at,
            subdirs=subdirs,
            records=recs,
        )
        page_path.write_text(rendered, encoding="utf-8")

def resolve_inputs(target: str, recursive: bool = True) -> list[Path]:
    """
    - File: include only if it looks like LightBurn
    - Dir: recurse by default (your desired behavior)
    - Glob: expand and filter
    """
    p = Path(target).expanduser()

    if p.exists() and p.is_file():
        return [p.resolve()] 
        #return [p.resolve()] if is_likely_lightburn_project(p) else []

    if p.exists() and p.is_dir():
        pattern = "**/*" if recursive else "*"
        files = [
            x for x in p.glob(pattern)
            if x.is_file() and not x.name.endswith("_thumbnail.png")
        ]
        #files = [x for x in p.glob(pattern) if x.is_file()]
        #files = [x for x in p.glob(pattern) if is_likely_lightburn_project(x)]
        return sorted({f.resolve() for f in files}, key=lambda x: str(x).lower())

    # glob pattern
    matches = glob.glob(target, recursive=True)
    files = [
        Path(m).expanduser()
        for m in matches
        if Path(m).is_file() and not Path(m).name.endswith("_thumbnail.png")
    ]
    #files = [Path(m).expanduser() for m in matches if Path(m).is_file()]
    #files = [f for f in files if is_likely_lightburn_project(f)]
    return sorted({f.resolve() for f in files}, key=lambda x: str(x).lower())

def md_escape_cell(text: str) -> str:
    if text is None:
        return ""
    t = text.replace("|", r"\|")
    t = t.replace("\n", "<br>")
    return t

def write_markdown_report(records, output_path: Path, root_for_rel: Path | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=PackageLoader("maker_file_index", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    )

    template = env.get_template("report.md.j2")

    generated_at = datetime.now().astimezone().strftime(
        "%B %d, %Y %I:%M %p"
    ).lstrip("0").replace("AM", "am").replace("PM", "pm")

    rendered = template.render(
        records=records,
        generated_at=generated_at,
    )
    output_path.write_text(rendered, encoding="utf-8")




def scan(target: str, recursive: bool = True, debug_plugins: bool = False) -> list[IndexRecord]:
    files = resolve_inputs(target, recursive=recursive)
    plugins = load_plugins()

    records: list[IndexRecord] = []
    for p in files:
        for plugin in plugins:
            if plugin.can_handle(p):
                if debug_plugins:
                    print(f"[plugin:{plugin.name}] {p}")
                records.append(plugin.index(p))
                break
        else:
            if debug_plugins:
                print(f"[no-plugin] {p}")
        # else: unsupported file type, skip for now

    return records
