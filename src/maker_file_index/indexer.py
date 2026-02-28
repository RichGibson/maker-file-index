from __future__ import annotations

import glob
from datetime import datetime
from pathlib import Path

from maker_file_index.plugins.loader import load_plugins
from maker_file_index.plugins.base import IndexRecord  # or whatever you named your generic record

plugins=load_plugins()

from maker_file_index.plugins.lightburn import (
    LightBurnInfo,
    extract_notes_and_thumbnail,
    is_likely_lightburn_project,
)


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


#def write_markdown_report(records: list[LightBurnInfo], output_path: Path, root_for_rel: Path | None = None) -> None:

def write_markdown_report(records: list[IndexRecord], output_path: Path, root_for_rel: Path | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# LightBurn Notes Report - {now_iso}")
    lines.append("")
    lines.append(f"- Files scanned: **{len(records)}**")
    lines.append("")
    lines.append("| Thumbnail | File | Notes | Error |")
    lines.append("|---|---|---|---|")

    for r in records:
        display_path = r.path
        if root_for_rel is not None:
            try:
                display_path = r.path.relative_to(root_for_rel)
            except Exception:
                display_path = r.path

        thumb = ""
        if r.thumbnail_path and str(r.thumbnail_path) not in {"", "."} and r.thumbnail_path.exists():
            thumb = f"<img src='{r.thumbnail_path}' height=256 width=256>"

        file_cell = md_escape_cell(str(display_path))
        notes_cell = md_escape_cell(r.notes)
        err_cell = md_escape_cell(r.error)

        lines.append(f"{thumb} | `{file_cell}` | {notes_cell} | {err_cell} |")

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")



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


#def scan_lightburn(target: str, recursive: bool = True) -> list[LightBurnInfo]:
#    files = resolve_inputs(target, recursive=recursive)
    #return [extract_notes_and_thumbnail(p) for p in files]
