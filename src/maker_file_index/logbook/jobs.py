"""Read LightBurn's job history CSV and group jobs into sessions."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Job:
    when: datetime
    device: str
    project: Path | None
    sent_file: str


def read_jobs(csv_path: Path) -> list[Job]:
    with open(csv_path, newline="", errors="replace") as f:
        return [
            Job(
                when=datetime.fromisoformat(row["Timestamp"]),
                device=row.get("Device") or "",
                project=Path(row["Project"]) if (row.get("Project") or "").strip() else None,
                sent_file=(row.get("Sent File") or "").strip(),
            )
            for row in csv.DictReader(f)
            if row.get("Timestamp")
        ]


def jobs_by_day(jobs: list[Job]) -> dict[date, list[Job]]:
    days: dict[date, list[Job]] = defaultdict(list)
    for job in jobs:
        days[job.when.date()].append(job)
    return dict(days)


def sessions(jobs: list[Job], gap: timedelta = timedelta(minutes=45)) -> list[list[Job]]:
    groups: list[list[Job]] = []
    for job in sorted(jobs, key=lambda j: j.when):
        if not groups or job.when - groups[-1][-1].when > gap:
            groups.append([])
        groups[-1].append(job)
    return groups
