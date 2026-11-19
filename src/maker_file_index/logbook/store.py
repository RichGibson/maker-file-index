"""Durable per-job settings under log/jobs/, so the big debug log can go away."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from maker_file_index.logbook.debuglog import StreamJob
from maker_file_index.logbook.ruida import Setting, decode_settings


def _job_path(log_dir: Path, started: datetime) -> Path:
    return Path(log_dir) / "jobs" / started.strftime("%Y-%m-%d") / f"{started:%H%M%S}.json"


def save_stream_job(log_dir: Path, job: StreamJob) -> Path:
    path = _job_path(log_dir, job.started)
    if path.exists():
        old = json.loads(path.read_text())
        if not old.get("truncated"):
            return path  # a complete record is final
        if job.truncated and len(job.raw) <= old.get("bytes", 0):
            return path  # keep the longer partial stream
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "started": job.started.isoformat(timespec="milliseconds"),
        "truncated": job.truncated,
        "bytes": len(job.raw),
        "settings": [
            {"speed_mm_s": s.speed_mm_s, "min_power": s.min_power, "max_power": s.max_power}
            for s in decode_settings(job.raw)
        ],
    }
    path.write_text(json.dumps(record, indent=1) + "\n")
    return path


def load_stored(log_dir: Path, day: date) -> dict[datetime, list[Setting]]:
    folder = Path(log_dir) / "jobs" / day.isoformat()
    stored: dict[datetime, list[Setting]] = {}
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text())
        stored[datetime.fromisoformat(record["started"])] = [Setting(**s) for s in record["settings"]]
    return stored


def match_stream(job_time: datetime, stored: dict[datetime, list[Setting]],
                 tolerance_s: float = 5.0) -> list[Setting] | None:
    best = min(stored, key=lambda t: abs((t - job_time).total_seconds()), default=None)
    if best is None or abs((best - job_time).total_seconds()) > tolerance_s:
        return None
    return stored[best]
