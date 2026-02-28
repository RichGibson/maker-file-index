from __future__ import annotations

import argparse
import sys
from pathlib import Path
import pdb

from maker_file_index.indexer import scan_lightburn, write_markdown_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index maker files (LightBurn first) with thumbnails and notes.")
    parser.add_argument("target", help="File, directory, or glob (quote globs).")
    parser.add_argument("-o", "--output", default="lightburn_notes.md", help="Output Markdown filename.")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="If target is a directory, do not scan subdirectories.",
    )
    parser.add_argument(
        "--relpath-root",
        default=None,
        help="If provided, file paths in the report are written relative to this directory.",
    )
    args = parser.parse_args(argv)

    recursive = not args.no_recursive
    records = scan_lightburn(args.target, recursive=recursive)

    if not records:
        print(f"ERROR: No LightBurn files found for target: {args.target}", file=sys.stderr)
        return 2

    out_path = Path(args.output).expanduser().resolve()
    root_for_rel = Path(args.relpath_root).resolve() if args.relpath_root else None
    write_markdown_report(records, out_path, root_for_rel=root_for_rel)

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

