from __future__ import annotations

from pathlib import Path


def thumbnail_path_for(source_path: Path, *, suffix: str = "_thumbnail.png") -> Path:
    """
    Standard thumbnail naming:
      foo.ext -> foo_thumbnail.png
    """
    return source_path.with_name(f"{source_path.stem}{suffix}")


def write_bytes(path: Path, data: bytes, *, overwrite: bool = False) -> Path:
    """
    Write thumbnail bytes to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    path.write_bytes(data)
    return path
