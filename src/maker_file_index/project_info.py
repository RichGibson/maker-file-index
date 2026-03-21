"""project-info: fast file inventory CLI for maker project directories."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass",
    ".c", ".cpp", ".h", ".hpp",
    ".java", ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".zsh",
    ".json", ".yaml", ".yml", ".toml", ".xml",
    ".md", ".txt",
}

MAKER_EXTENSIONS = {
    ".lbrn", ".lbrn2",  # LightBurn
    ".stl",              # STL
    ".dxf",              # DXF
    ".svg",              # SVG
    ".3mf",              # 3MF
    ".scad",             # OpenSCAD
    ".cdr",              # Corel Draw
}

MAKER_LABELS = {
    ".lbrn":  "LightBurn",
    ".lbrn2": "LightBurn",
    ".stl":   "STL",
    ".dxf":   "DXF",
    ".svg":   "SVG",
    ".3mf":   "3MF",
    ".scad":  "OpenSCAD",
    ".cdr":   "Corel Draw",
}


def _fmt_size(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def collect_files(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        return [p for p in root.rglob("*") if p.is_file()]
    else:
        return [p for p in root.iterdir() if p.is_file()]


def _count_lines(path: Path) -> int | None:
    """Return line count for a text file, or None if it can't be read as text."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


def analyze(files: list[Path]) -> dict:
    total_size = 0
    ext_counts: dict[str, int] = defaultdict(int)
    ext_sizes: dict[str, int] = defaultdict(int)
    ext_lines: dict[str, int] = defaultdict(int)
    recent: list[tuple[float, Path]] = []

    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        size = st.st_size
        mtime = st.st_mtime
        total_size += size

        ext = f.suffix.lower()
        ext_counts[ext] += 1
        ext_sizes[ext] += size

        if ext in CODE_EXTENSIONS:
            lines = _count_lines(f)
            if lines is not None:
                ext_lines[ext] += lines

        recent.append((mtime, f))

    recent.sort(key=lambda x: x[0], reverse=True)
    top_recent = recent[:5]

    return {
        "total_files": len(files),
        "total_size": total_size,
        "by_extension": {
            ext: {
                "count": ext_counts[ext],
                "size": ext_sizes[ext],
                **({"lines": ext_lines[ext]} if ext in ext_lines else {}),
            }
            for ext in sorted(ext_counts, key=lambda e: ext_counts[e], reverse=True)
        },
        "recent": [(mtime, str(path)) for mtime, path in top_recent],
    }


def print_report(data: dict, root: Path) -> None:
    total = data["total_files"]
    size = data["total_size"]
    print(f"\nDirectory: {root}")
    print(f"  {total} file{'s' if total != 1 else ''}  —  {_fmt_size(size)} total\n")

    by_ext = data["by_extension"]
    if not by_ext:
        print("  (no files found)")
        return

    # Separate maker types from others
    maker_exts = {e: v for e, v in by_ext.items() if e in MAKER_EXTENSIONS}
    other_exts = {e: v for e, v in by_ext.items() if e not in MAKER_EXTENSIONS}

    if maker_exts:
        print("  Maker files:")
        for ext, info in sorted(maker_exts.items(), key=lambda x: x[1]["count"], reverse=True):
            label = MAKER_LABELS.get(ext, ext)
            print(f"    {ext or '(no ext)':12s}  {info['count']:5d}  {_fmt_size(info['size']):>10s}  [{label}]")

    if other_exts:
        code_exts = {e: v for e, v in other_exts.items() if e in CODE_EXTENSIONS}
        non_code_exts = {e: v for e, v in other_exts.items() if e not in CODE_EXTENSIONS}

        if code_exts:
            print("\n  Code / text files:")
            for ext, info in sorted(code_exts.items(), key=lambda x: x[1]["count"], reverse=True):
                lines_str = f"  {info['lines']:,} lines" if "lines" in info else ""
                print(f"    {ext or '(no ext)':12s}  {info['count']:5d}  {_fmt_size(info['size']):>10s}{lines_str}")

        if non_code_exts:
            print("\n  Other files:")
            for ext, info in sorted(non_code_exts.items(), key=lambda x: x[1]["count"], reverse=True):
                print(f"    {ext or '(no ext)':12s}  {info['count']:5d}  {_fmt_size(info['size']):>10s}")

    if data["recent"]:
        import time as _time
        print("\n  Recently modified (top 5):")
        for mtime, path in data["recent"]:
            ts = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(mtime))
            rel = Path(path).relative_to(root) if Path(path).is_relative_to(root) else Path(path)
            print(f"    {ts}  {rel}")

    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="project-info",
        description="Fast file inventory for a maker project directory.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not scan subdirectories.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of plain text.",
    )
    args = parser.parse_args(argv)

    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 1

    recursive = not args.no_recursive
    files = collect_files(root, recursive=recursive)
    data = analyze(files)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print_report(data, root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
