from __future__ import annotations

from pathlib import Path

def thumbnail_is_fresh(source_path: Path, thumb_path: Path) -> bool:
    """
    Return True if thumbnail exists and is newer than the source file.
    """
    if not thumb_path.exists():
        return False

    try:
        return thumb_path.stat().st_mtime >= source_path.stat().st_mtime
    except OSError:
        return False

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
