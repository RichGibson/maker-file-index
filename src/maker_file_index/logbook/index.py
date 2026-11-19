"""The logbook's front page: every day, newest first, with a one-line summary."""

from __future__ import annotations

import re
from datetime import date, datetime

from maker_file_index.logbook.daypage import EMPTY_NOTE, GENERATED_MARK
from maker_file_index.logbook.jobs import Job, sessions
from maker_file_index.logbook.ruida import Setting, grid

_DAY_NOTE = re.compile(r"<!-- notes:start -->(.*?)<!-- notes:end -->", re.DOTALL)
_MAX_NOTE = 140
_MAX_PROJECTS = 4


def day_note_summary(page: str) -> str | None:
    """First line of plain text in a day page's notes block, without Markdown emphasis."""
    m = _DAY_NOTE.search(page)
    if not m:
        return None
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line == EMPTY_NOTE or line[0] in "!<|#":
            continue
        line = line.replace("**", "").replace("*", "")
        return line if len(line) <= _MAX_NOTE else line[: _MAX_NOTE - 3].rstrip() + "..."
    return None


def _projects(jobs: list[Job]) -> str:
    names: list[str] = []
    for job in jobs:
        name = job.project.stem if job.project else "(unsaved)"
        if name not in names:
            names.append(name)
    shown = ", ".join(names[:_MAX_PROJECTS])
    return shown + (f" +{len(names) - _MAX_PROJECTS} more" if len(names) > _MAX_PROJECTS else "")


def _summary(jobs: list[Job], stored: dict[datetime, list[Setting]]) -> str:
    jobs = sorted(jobs, key=lambda j: j.when)
    n, s = len(jobs), len(sessions(jobs))
    tests = sum(1 for settings in stored.values() if grid(settings))
    parts = [f"{n} job{'s' if n != 1 else ''}",
             f"{jobs[0].when:%H:%M} to {jobs[-1].when:%H:%M}",
             f"{s} session{'s' if s != 1 else ''}",
             _projects(jobs)]
    if tests:
        parts.append(f"{tests} material test{'s' if tests != 1 else ''}")
    return " · ".join(parts)


def render_index(by_day: dict[date, list[Job]], stored_by_day: dict[date, dict[datetime, list[Setting]]],
                 day_notes: dict[date, str]) -> str:
    days = sorted(by_day, reverse=True)
    total = sum(len(by_day[d]) for d in days)
    lines = [GENERATED_MARK, "# Laser log", ""]
    if days:
        lines += [f"{len(days):,} days · {total:,} jobs · {days[-1]:%b %-d, %Y} to {days[0]:%b %-d, %Y}", ""]
    lines += ["## About this laser", "", "<!-- notes:about:start -->", "<!-- notes:about:end -->", ""]
    month = None
    for d in days:
        if (d.year, d.month) != month:
            if month is not None:
                lines.append("")
            month = (d.year, d.month)
            lines += [f"## {d:%B %Y}", ""]
        lines.append(f"- **[{d:%a %b %-d}]({d.isoformat()}.md)** · "
                     f"{_summary(by_day[d], stored_by_day.get(d, {}))}")
        if day_notes.get(d):
            lines.append(f"  {day_notes[d]}")
    return "\n".join(lines) + "\n"
