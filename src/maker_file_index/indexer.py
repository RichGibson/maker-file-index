from __future__ import annotations

import glob
from datetime import datetime
from pathlib import Path
import os
import pdb

from maker_file_index.plugins.loader import load_plugins
from maker_file_index.plugins.base import IndexRecord  # or whatever you named your generic record
from jinja2 import Environment, PackageLoader, select_autoescape
from collections import defaultdict, Counter

plugins=load_plugins()

#from maker_file_index.plugins.lightburn import (
#    LightBurnInfo,
#    extract_notes_and_thumbnail,
#    is_likely_lightburn_project,
#)

def group_by_directory(records):
    grouped = defaultdict(list)
    for r in records:
        grouped[r.directory].append(r)

    print(f"in group by directory")
    return grouped

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






def scan(target: str, recursive: bool = True, debug_plugins: bool = False) -> list[IndexRecord]:
    files = resolve_inputs(target, recursive=recursive)
    plugins = load_plugins()
    no_plugin_count = Counter()
    plugin_count = Counter()
    records: list[IndexRecord] = []
    for p in files:
        for plugin in plugins:
            if plugin.can_handle(p):
                if debug_plugins:
                    print(f"[plugin:{plugin.name}] {p}")
                plugin_count[p.suffix.lower() or "<no-ext>"] += 1
                records.append(plugin.index(p))
                break
        else:
            if debug_plugins:
                print(f"[no-plugin] {p}")
                no_plugin_count[p.suffix.lower() or "<no-ext>"] += 1
        # else: unsupported file type, skip for now
    if debug_plugins and no_plugin_count:
        print("\nNo-plugin summary by extension:")
        for ext, n in sorted(no_plugin_count.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {ext}: {n}")
    print("\nplugin summary by extension:")
    for ext, n in sorted(plugin_count.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {ext}: {n}")
    
    return records
