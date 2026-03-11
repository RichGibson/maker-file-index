from __future__ import annotations

from pathlib import Path


# Extensions of files we generate (and are therefore safe to delete)
_OWNED_SUFFIXES = {".html", ".md", ".png", ".bmp"}

# Extensions that get a detail page
_DETAIL_EXTS = {"lbrn2", "lbrn", "stl", "3mf", "svg", "dxf", "scad", "cdr"}


def cleanup_stale_output(records, out_dir: Path, root_dir: Path) -> int:
    """
    Delete generated files in out_dir/dirs/ that have no corresponding source record.
    Only touches files with extensions we own (.html, .md, .png, .bmp).
    Returns the number of files deleted.
    """
    out_dir = out_dir.resolve()
    root_dir = root_dir.resolve()
    dirs_root = out_dir / "dirs"

    if not dirs_root.exists():
        return 0

    # Build the set of paths we expect to exist
    expected: set[Path] = set()

    known_dir_rels: set[Path] = set()

    for r in records:
        try:
            rel = r.path.parent.relative_to(root_dir)
        except ValueError:
            continue

        known_dir_rels.add(rel)

        ext = r.path.suffix.lower().lstrip(".")
        if ext in _DETAIL_EXTS:
            expected.add(dirs_root / rel / (r.path.stem + ".html"))
            expected.add(dirs_root / rel / (r.path.stem + ".md"))

        # Thumbnail — only track if it lives inside out_dir
        if r.thumbnail_path and str(r.thumbnail_path) not in ("", ".", "./"):
            tp = Path(r.thumbnail_path).resolve()
            if tp.is_relative_to(out_dir):
                expected.add(tp)

    # Directory index pages — walk up from each known dir to dirs_root
    for rel in known_dir_rels:
        cur = rel
        while True:
            expected.add(dirs_root / cur / "index.html")
            expected.add(dirs_root / cur / "index.md")
            if not cur.parts:
                break
            cur = cur.parent

    # dirs_root itself always has index pages
    expected.add(dirs_root / "index.html")
    expected.add(dirs_root / "index.md")

    # Determine which subdirectories of dirs_root to inspect.
    # Only walk directories that were actually scanned (in known_dir_rels) plus
    # any child directories of those that exist in dirs_root but whose source
    # directory no longer exists (orphaned from a prior run within the same scope).
    # This prevents wiping output from other directories that share the same
    # output dir but were produced by a different scan invocation.
    scoped_dirs: set[Path] = {dirs_root}
    for rel in known_dir_rels:
        # Add each ancestor up to (but not including) dirs_root
        cur = dirs_root / rel
        while cur != dirs_root:
            scoped_dirs.add(cur)
            cur = cur.parent

    # Also include any subdirectories of scoped_dirs that exist in the output
    # but whose source counterpart no longer exists — these are orphans that
    # should still be cleaned up within the scanned scope.
    for d in scoped_dirs.copy():
        if d.exists():
            for child in d.iterdir():
                if child.is_dir():
                    source_counterpart = root_dir / child.relative_to(dirs_root)
                    if not source_counterpart.exists():
                        scoped_dirs.add(child)

    # Walk only within scoped directories and delete stale owned files
    deleted = 0
    all_scoped = sorted(scoped_dirs, key=lambda p: len(p.parts), reverse=True)
    for scan_dir in all_scoped:
        if not scan_dir.exists():
            continue
        for f in sorted(scan_dir.iterdir(), key=lambda p: len(p.parts), reverse=True):
            if f.is_file() and f.suffix.lower() in _OWNED_SUFFIXES:
                if f not in expected:
                    f.unlink()
                    deleted += 1
                    print(f"  Removed stale: {f.relative_to(out_dir)}")
            elif f.is_dir() and f in scoped_dirs:
                try:
                    f.rmdir()  # only succeeds if empty
                except OSError:
                    pass

    return deleted
