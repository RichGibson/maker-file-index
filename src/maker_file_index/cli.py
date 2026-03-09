from __future__ import annotations

import argparse
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

try:
    __version__ = version("maker-file-index")
except PackageNotFoundError:
    __version__ = "unknown"

from maker_file_index.indexer import scan
from maker_file_index.cleanup import cleanup_stale_output
from maker_file_index.renderers.markdown import write_markdown_report, write_directory_pages, write_detail_pages_markdown
from maker_file_index.renderers.html import write_directory_pages_html, write_landing_page_html, write_lightburn_detail_pages_html, write_stl_detail_pages_html, write_3mf_detail_pages_html, write_svg_detail_pages_html, write_dxf_detail_pages_html, write_scad_detail_pages_html, write_cdr_detail_pages_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index maker files (LightBurn first) with thumbnails and notes.")
    parser.add_argument("--version", action="version", version=f"maker-file-index {__version__}")
    parser.add_argument(
    "target",
    nargs="?",
    default=".",
    help="File, directory, or glob (quote globs)",
)
    parser.add_argument("-o", "--output-dir", default="maker_file_data", help="Output directory for all generated files (default: maker_file_data)")
    parser.add_argument("--alongside-source", action="store_true", help="Write all output (HTML, markdown, thumbnails) into the source directory tree instead of a separate output directory. WARNING: may create or overwrite files in your source directory.")
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
    parser.add_argument(
    "--debug-plugins",
    action="store_true",
    help="Show which plugin handles each file.",
)
    args = parser.parse_args(argv)

    recursive = not args.no_recursive
    root_dir = Path(args.target).expanduser().resolve() if Path(args.target).expanduser().is_dir() else Path(args.target).expanduser().resolve().parent
    root_for_rel = Path(args.relpath_root).resolve() if args.relpath_root else None

    alongside_source = args.alongside_source
    if alongside_source:
        output_dir = None  # thumbnails go alongside source files
    else:
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    out_dir = output_dir if output_dir else root_dir
    notes_path = out_dir / "maker_file_notes.md"

    records = scan(args.target, recursive=recursive, debug_plugins=args.debug_plugins, output_dir=output_dir)

    if not records:
        print(f"ERROR: No supported files found for target: {args.target}", file=sys.stderr)
        return 2

    print(f"\nWriting markdown report ({len(records)} files)...")
    write_markdown_report(records, notes_path, root_for_rel=root_for_rel, root_dir=root_dir)
    write_directory_pages(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing markdown detail pages...")
    write_detail_pages_markdown(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing HTML directory pages...")
    write_directory_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing landing page...")
    write_landing_page_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing LightBurn detail pages...")
    write_lightburn_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing STL detail pages...")
    write_stl_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing 3MF detail pages...")
    write_3mf_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing SVG detail pages...")
    write_svg_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing DXF detail pages...")
    write_dxf_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing OpenSCAD detail pages...")
    write_scad_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    print("Writing Corel Draw detail pages...")
    write_cdr_detail_pages_html(records, out_dir=out_dir, root_dir=root_dir)

    if output_dir is not None:
        print("Cleaning up stale output...")
        n = cleanup_stale_output(records, out_dir=out_dir, root_dir=root_dir)
        if n:
            print(f"  Removed {n} stale file{'s' if n != 1 else ''}.")

    print("\nDone.")
    print(str(notes_path))
    print(str(out_dir / "dirs" / "index.md"))
    print(str(out_dir / "index.html"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

