#!/usr/bin/env python3
"""
Extract LightBurn XML <Notes> from one or more LightBurn project files and
write a single Markdown report.

Input can be:
- a single filename
- a directory (we'll scan for likely LightBurn XML project files)
- a wildcard/glob (quoted in your shell), e.g. "*.lbrn2" or "projects/**/*.lbrn2"

Output:
- a Markdown file listing each file and its Notes text (blank if missing)

Examples:
  python lb_notes_report.py ./angel_all_lines.lbrn2
  python lb_notes_report.py ./projects/
  python lb_notes_report.py "./projects/**/*.lbrn2" --recursive
  python lb_notes_report.py "*.lbrn2" -o lightburn_notes.md
"""

from __future__ import annotations

import argparse
import os
import sys
import glob
import pdb
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from datetime import datetime



LIKELY_EXTS = {".lbrn2", ".lbrn"}

###


import base64
import binascii


"""
Extract the embedded thumbnail from a LightBurn project file (usually .lbrn2) and
write it out as a PNG (or whatever the embedded bytes actually are).

"""
def _find_thumbnail_b64(root: ET.Element) -> str:
    """
    LightBurn .lbrn2 commonly stores thumbnails like:
      <Thumbnail Source="iVBORw0K..."/>

    But we also try a couple other plausible layouts, just in case:
      <Thumbnail>iVBORw0K...</Thumbnail>
      <Thumbnail><Source>iVBORw0K...</Source></Thumbnail>
    """
    # 1) The common case: attribute Source on <Thumbnail />
    for thumb in root.iter("Thumbnail"):
        b64 = (thumb.attrib.get("Source") or "").strip()
        if b64:
            return b64

        # 2) Sometimes text content might hold base64
        if thumb.text and thumb.text.strip():
            return thumb.text.strip()

        # 3) Nested <Source> element
        src = thumb.find("Source")
        if src is not None and src.text and src.text.strip():
            return src.text.strip()

    raise ValueError("No thumbnail found. Expected a <Thumbnail> element with base64 data.")


def _decode_b64(data_b64: str) -> bytes:
    # LightBurn base64 is typically unpadded; add padding if necessary.
    data_b64 = "".join(data_b64.split())  # remove whitespace/newlines
    pad = (-len(data_b64)) % 4
    if pad:
        data_b64 += "=" * pad

    try:
        return base64.b64decode(data_b64, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Thumbnail base64 decode failed: {e}") from e


def _sniff_extension(blob: bytes) -> str:
    # Default assumption: PNG. But let’s sniff a few common signatures.
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith(b"GIF87a") or blob.startswith(b"GIF89a"):
        return ".gif"
    if blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def extract_thumbnail(input_path: Path, output_path: Path | None = None, overwrite: bool = False) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Parse XML (LightBurn .lbrn2 is plain XML)
    try:
        tree = ET.parse(input_path)
    except ET.ParseError as e:
        raise ValueError(f"XML parse failed. Is this a valid LightBurn XML project file? {e}") from e

    root = tree.getroot()
    b64 = _find_thumbnail_b64(root)
    blob = _decode_b64(b64)

    # Choose output path
    if output_path is None:
        ext = _sniff_extension(blob)
        output_path = input_path.with_name(f"{input_path.stem}_thumbnail{ext}")

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {output_path} (use --overwrite)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(blob)
    return output_path


#def main(argv: list[str]) -> int:
#    parser = argparse.ArgumentParser(description="Extract the embedded thumbnail from a LightBurn project file.")
#    parser.add_argument("input", type=Path, help="Path to LightBurn project file (e.g., .lbrn2)")
#    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file path (default: <stem>_thumbnail.png)")
#    parser.add_argument("--overwrite", action="store_true", help="Overwrite output file if it exists")
#    args = parser.parse_args(argv)
#
#    try:
#        out = extract_thumbnail(args.input, args.output, overwrite=args.overwrite)
#    except Exception as e:
#        print(f"ERROR: {e}", file=sys.stderr)
#        return 2
#
#    print(str(out))
#    return 0


#if __name__ == "__main__":
    #raise SystemExit(main(sys.argv[1:]))

#pdb.set_trace()
###



@dataclass(frozen=True)
class NotesRecord:
    path: Path
    notes: str
    #thumbnail_path: Path
    thumbnail_path: Path = Path("")
    error: str = ""


#def is_likely_lightburn_project(path: Path) -> bool:
    #if not path.is_file():
        #return False
    #if path.suffix.lower() in LIKELY_EXTS:
        #return True
    ## Also allow XML-ish files with unknown extension (people rename things)
    ## but avoid huge binaries by basic size check.
    #try:
        #if path.stat().st_size > 50_000_000:
            #return False
    #except OSError:
        #return False
    #return False

def is_likely_lightburn_project(path: Path) -> bool:

    flag=path.is_file() and path.suffix.lower() in LIKELY_EXTS
    print(f"PATH: {path} FLAG: {flag}")

    return path.is_file() and path.suffix.lower() in LIKELY_EXTS

def FOOis_likely_lightburn_project(path: Path) -> bool:
    """
    Fast heuristic: is this probably a LightBurn XML file?

    Strategy:
    - Must be a file
    - Skip huge files
    - Reject obvious binary
    - Look for LightBurn XML markers
    """
    if not path.is_file():
        return False

    try:
        size = path.stat().st_size
    except OSError:
        return False

    if size <= 0 or size > 200_000_000:
        return False

    try:
        prefix = path.read_bytes()[:65536]
    except OSError:
        return False

    # Reject obvious binary
    if b"\x00" in prefix[:4096]:
        return False

    text = prefix.decode("utf-8", errors="ignore")

    markers = (
        "<LightBurnProject",
        "<CutSetting",
        "<Thumbnail",
        "<Notes",
        "AppVersion=",
        "Device=",
    )

    if any(m in text for m in markers):
        return True

    # fallback: extension hint + looks like XML
    if path.suffix.lower() in LIKELY_EXTS:
        stripped = text.lstrip()
        if stripped.startswith("<?xml") or stripped.startswith("<"):
            return True

    return False


def resolve_inputs(target: str, recursive: bool = False) -> list[Path]:
    p = Path(target)

    paths: list[Path] = []

    if p.exists() and p.is_file():
        # ✅ only accept likely LightBurn files
        paths = [p] if is_likely_lightburn_project(p) else []

    elif p.exists() and p.is_dir():
        candidates = list(p.rglob("*")) if recursive else list(p.glob("*"))
        paths = [c for c in candidates if is_likely_lightburn_project(c)]

    else:
        matches = glob.glob(target, recursive=True)
        candidates = [Path(m) for m in matches if Path(m).is_file()]

        # ✅ always filter here too (don’t keep random files)
        paths = [c for c in candidates if is_likely_lightburn_project(c)]

    uniq = sorted({pp.resolve() for pp in paths}, key=lambda x: str(x).lower())
    return uniq

def extract_notes_from_lightburn_xml(path: Path) -> NotesRecord:
    """
    Parse XML and return Notes text or blank.

    LightBurn stores notes in at least two ways:
      1) <Notes>some text</Notes>
      2) <Notes Notes="some text with &#10; newlines" ... />

    We support both.
    """
    try:
        print(f"processing {path}")
        tree = ET.parse(path)
        root = tree.getroot()

        notes_el = root.find(".//Notes")
        if notes_el is None:
            return NotesRecord(path=path, notes="")

        # Case 1: attribute form <Notes Notes="..."/>
        attr_val = (notes_el.attrib.get("Notes") or "").strip()
        if attr_val:
            notes_text = attr_val

        # Case 2: text form <Notes>...</Notes>
        else:
            notes_text = (notes_el.text or "").strip()

        # Normalize newlines
        notes_text = notes_text.replace("\r\n", "\n").replace("\r", "\n").strip()

        print(f"my ass {path}")
        thumbnail_path=extract_thumbnail(path, overwrite=True)
        return NotesRecord(path=path, notes=notes_text, thumbnail_path=thumbnail_path)

    except ET.ParseError as e:
        return NotesRecord(path=path, notes="", error=f"XML parse error: {e}")
    except Exception as e:
        return NotesRecord(path=path, notes="", error=f"{type(e).__name__}: {e}")


def md_escape_cell(text: str) -> str:
    """
    Escape Markdown table cell content:
    - Replace newlines with <br>
    - Escape pipe characters
    """
    if text is None:
        return ""
    t = text.replace("|", r"\|")
    t = t.replace("\n", "<br>")
    return t


def write_markdown_report(records: list[NotesRecord], output_path: Path, root_for_rel: Path | None = None) -> None:
    """
    Writes a Markdown table:
      | File | Notes | Error |
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# LightBurn Notes Report - {now_iso}")
    lines.append("")
    lines.append(f"- Files scanned: **{len(records)}**")
    lines.append("")
    lines.append("|Thumbnail | File | Notes | Error |")
    lines.append("|---|---|---|---|")

    for r in records:
        display_path = r.path
        if root_for_rel is not None:
            try:
                display_path = r.path.relative_to(root_for_rel)
            except Exception:
                display_path = r.path
        thumbnail_cell=f"<img src='{r.thumbnail_path}' height=256 width=256>"
        #thumbnail_cell=f"![thumbnail]({r.thumbnail_path})"
        file_cell = md_escape_cell(str(display_path))
        notes_cell = md_escape_cell(r.notes)
        err_cell = md_escape_cell(r.error)

        lines.append(f"{thumbnail_cell}| `{file_cell}` | {notes_cell} | {err_cell} |")

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown report listing LightBurn project files and their <Notes> content."
    )
    parser.add_argument(
        "target",
        help="A filename, directory, or glob (quote globs to avoid shell expansion differences).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="lightburn_notes.md",
        help="Output Markdown filename (default: lightburn_notes.md).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When target is a directory, scan recursively.",
    )
    parser.add_argument(
        "--relpath-root",
        default=None,
        help="If provided, file paths in the report are written relative to this directory.",
    )
    args = parser.parse_args(argv)

    files = resolve_inputs(args.target, recursive=args.recursive)
    if not files:
        print(f"ERROR: No files found for target: {args.target}", file=sys.stderr)
        return 2

    records = [extract_notes_from_lightburn_xml(p) for p in files]

    root_for_rel = Path(args.relpath_root).resolve() if args.relpath_root else None
    out_path = Path(args.output).expanduser().resolve()
    write_markdown_report(records, out_path, root_for_rel=root_for_rel)

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

pdb.set_trace()
