"""Render one Markdown page per day of laser use, keeping hand-written notes."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from jinja2 import Environment, PackageLoader, select_autoescape

from maker_file_index.logbook.jobs import Job, sessions
from maker_file_index.logbook.projectfile import FileVersion
from maker_file_index.logbook.ruida import Setting, grid
from maker_file_index.logbook.store import match_stream

GENERATED_MARK = "<!-- generated-by: maker-file-index laser-log -->"
FILES_ROOT = Path.home() / "projects" / "laserblog" / "files"
EMPTY_NOTE = "✎"

_NOTES = re.compile(r"<!-- notes(?::([\w-]+))?:start -->(.*?)<!-- notes(?::\1)?:end -->", re.DOTALL)

_env = Environment(
    loader=PackageLoader("maker_file_index", "templates"),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def _num(x: float | None) -> str:
    if x is None:
        return "?"
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _power(lo: float | None, hi: float | None) -> str:
    if lo is None or hi is None or lo == hi:
        return f"{_num(hi if hi is not None else lo)}%"
    return f"{_num(lo)} to {_num(hi)}%"


def _project_label(project: Path | None, files_root: Path) -> str:
    if project is None:
        return "(unsaved project)"
    try:
        return project.relative_to(files_root).as_posix()
    except ValueError:
        return str(project)


def _settings_summary(settings: list[Setting] | None) -> str:
    if not settings:
        return "not captured"
    g = grid(settings)
    if g:
        speeds, powers = g
        return (f"material test grid: {_num(speeds[0])} to {_num(speeds[-1])} mm/s"
                f" × {_num(powers[0])} to {_num(powers[-1])}%")
    parts = [f"{_num(s.speed_mm_s)} mm/s {_power(s.min_power, s.max_power)}" for s in settings[:4]]
    if len(settings) > 4:
        parts.append(f"+{len(settings) - 4} more")
    return "; ".join(parts)


def render_day(day: date, jobs: list[Job], stored: dict[datetime, list[Setting]],
               versions: Callable[[Path, datetime], FileVersion],
               files_root: Path = FILES_ROOT) -> str:
    day_jobs = sorted((j for j in jobs if j.when.date() == day), key=lambda j: j.when)
    groups = []
    number = 0
    projects: list[str] = []
    tests = []
    for group in sessions(day_jobs):
        rows, grids, files = [], [], {}
        for j in group:
            number += 1
            settings = match_stream(j.when, stored)
            label = _project_label(j.project, files_root)
            if label not in projects:
                projects.append(label)
            g = grid(settings) if settings else None
            if g:
                grids.append({"time": f"{j.when:%H:%M:%S}", "id": f"test-{j.when:%H%M%S}", "speeds": [_num(v) for v in g[0]],
                              "powers": [_num(p) for p in g[1]]})
                tests.append(f"{j.when:%H:%M:%S}")
            rows.append({"n": number, "time": f"{j.when:%H:%M:%S}", "id": f"job-{j.when:%H%M%S}",
                         "project": label, "settings": _settings_summary(settings)})
            if j.project is not None and label not in files:
                v = versions(j.project, j.when)
                files[label] = {"source": v.source, "layers": [
                    {"name": layer.name, "mode": layer.mode, "speed": _num(layer.speed),
                     "power": _power(layer.min_power, layer.max_power),
                     "passes": layer.passes, "shapes": layer.shapes}
                    for layer in v.layers]}
        groups.append({"start": f"{group[0].when:%H:%M}", "end": f"{group[-1].when:%H:%M}",
                       "count": len(group), "rows": rows, "grids": grids, "files": files})
    return _env.get_template("log_day.md.j2").render(
        mark=GENERATED_MARK, day=day, title=day.strftime("%a %b %-d, %Y"),
        device=day_jobs[0].device if day_jobs else "", sessions=groups, projects=projects,
        tests=tests, total=len(day_jobs), empty=EMPTY_NOTE)


def merge_notes(existing: str, generated: str) -> str:
    """Carry every notes block from `existing` into `generated`; never drop text."""
    old = {m.group(1) or "day": m.group(2) for m in _NOTES.finditer(existing)}
    used: set[str] = set()

    def keep(m: re.Match) -> str:
        key = m.group(1) or "day"
        if key not in old:
            return m.group(0)
        used.add(key)
        whole, start = m.group(0), m.start(0)
        return whole[: m.start(2) - start] + old[key] + whole[m.end(2) - start:]

    merged = _NOTES.sub(keep, generated)
    orphans = {k: v for k, v in old.items() if k not in used and v.strip() not in ("", EMPTY_NOTE)}
    if orphans:
        merged = merged.rstrip("\n") + "\n\n## Orphaned notes\n\n" + "\n\n".join(
            f"<!-- notes:{k}:start -->{v}<!-- notes:{k}:end -->" for k, v in orphans.items()) + "\n"
    return merged
