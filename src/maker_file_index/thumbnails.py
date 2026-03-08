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

def thumbnail_path_for(
    source_path: Path,
    *,
    suffix: str = "_thumbnail.png",
    thumb_root: Path | None = None,
    scan_root: Path | None = None,
) -> Path:
    """
    Standard thumbnail naming:
      foo.ext -> foo_thumbnail.png

    When thumb_root and scan_root are both provided, the thumbnail is placed
    under thumb_root mirroring the source directory structure:
      thumb_root / rel_dir / foo_thumbnail.png
    """
    if thumb_root is not None and scan_root is not None:
        try:
            rel_dir = source_path.parent.relative_to(scan_root)
        except ValueError:
            rel_dir = Path(source_path.parent.name)
        return thumb_root / rel_dir / f"{source_path.stem}{suffix}"
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
