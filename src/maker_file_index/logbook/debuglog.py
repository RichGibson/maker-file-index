"""Split LightBurn's debug log into the byte streams of individual jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3})\s")
_HEADER_DATE = re.compile(r'"\w{3} (\w{3} \d{1,2} \d{4})"')
_OUT = re.compile(r' O: "([0-9a-fA-F]*)("?)')


@dataclass
class StreamJob:
    started: datetime
    raw: bytes = b""
    truncated: bool = False
    _buf: bytearray = field(default_factory=bytearray, repr=False, compare=False)


def read_stream_jobs(path: Path) -> list[StreamJob]:
    try:
        text = Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return []

    day: datetime | None = None
    last_time: timedelta | None = None
    jobs: list[StreamJob] = []

    for line in text.splitlines():
        if day is None:
            m = _HEADER_DATE.search(line)
            if m:
                day = datetime.strptime(m.group(1), "%b %d %Y")
        t = _TIME.match(line)
        if t and day is not None:
            h, mi, s, ms = (int(x) for x in t.groups())
            now = timedelta(hours=h, minutes=mi, seconds=s, milliseconds=ms)
            if last_time is not None and now < last_time:
                day += timedelta(days=1)
            last_time = now
        if "Protocol::GenerateCuts" in line and day is not None and last_time is not None:
            jobs.append(StreamJob(started=day + last_time))
            continue
        out = _OUT.search(line)
        if out and jobs:
            hexstr, quote = out.groups()
            job = jobs[-1]
            job._buf += bytes.fromhex(hexstr[: len(hexstr) // 2 * 2])
            if not quote or len(hexstr) % 2:
                job.truncated = True

    for job in jobs:
        job.raw = bytes(job._buf)
    return jobs
