"""Layer settings of a LightBurn project, as the file was at a given time."""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from maker_file_index.plugins.lightburn import _lb_parse_cut_settings


@dataclass(frozen=True)
class Layer:
    index: int
    name: str
    mode: str
    speed: float | None
    min_power: float | None
    max_power: float | None
    passes: int
    shapes: int


@dataclass(frozen=True)
class FileVersion:
    source: str
    layers: list[Layer] = field(default_factory=list)


def layers_from_bytes(xml: bytes) -> list[Layer]:
    root = ET.fromstring(xml)
    used = Counter(s.get("CutIndex") for s in root.iter("Shape") if s.get("CutIndex") is not None)
    return [
        Layer(
            index=cs.index,
            name=cs.name,
            mode=cs.layer_type,
            speed=cs.speed,
            min_power=cs.min_power,
            max_power=cs.max_power,
            passes=cs.num_passes,
            shapes=used.get(str(cs.index), 0),
        )
        for cs in sorted(_lb_parse_cut_settings(root).values(), key=lambda c: c.index)
    ]


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out.stdout.decode(errors="replace")


def _commit_before(top: Path, rel: str, when: datetime) -> tuple[int, str] | None:
    out = _git(top, "log", "-1", f"--before={when.isoformat()}", "--format=%ct %h", "--", rel)
    if not out or not out.strip():
        return None
    ts, short = out.split()
    return int(ts), short


def _from_git(project: Path, when: datetime) -> FileVersion | None:
    if not project.parent.is_dir():
        return None
    top = _git(project.parent, "rev-parse", "--show-toplevel")
    if not top:
        return None
    top_path = Path(top.strip())
    candidates = []
    for path in (project, project.with_name(f"{project.stem}_backup{project.suffix}")):
        try:
            rel = path.resolve().relative_to(top_path.resolve()).as_posix()
        except ValueError:
            return None
        found = _commit_before(top_path, rel, when)
        if found:
            candidates.append((found[0], found[1], rel))
    if not candidates:
        return None
    _, short, rel = max(candidates)
    try:
        data = subprocess.run(["git", "-C", str(top_path), "show", f"{short}:{rel}"],
                              capture_output=True, check=True).stdout
        return FileVersion(f"git {short}", layers_from_bytes(data))
    except (subprocess.CalledProcessError, ET.ParseError):
        return None


def version_at(project: Path, when: datetime) -> FileVersion:
    project = Path(project)
    from_git = _from_git(project, when)
    if from_git:
        return from_git
    if project.is_file():
        try:
            return FileVersion("current file", layers_from_bytes(project.read_bytes()))
        except ET.ParseError:
            return FileVersion("current file", [])
    return FileVersion("missing", [])
