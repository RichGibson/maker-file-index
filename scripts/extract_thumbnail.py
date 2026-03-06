#!/usr/bin/env python3
"""
Standalone LightBurn thumbnail extractor / debugger.

Usage:
    python scripts/extract_thumbnail.py file.lbrn2
    python scripts/extract_thumbnail.py file.lbrn2 -o thumb.png
    python scripts/extract_thumbnail.py file.lbrn2 --debug
"""
from __future__ import annotations

import argparse
import base64
import binascii
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def sniff_extension(blob: bytes) -> str:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith(b"GIF87a") or blob.startswith(b"GIF89a"):
        return ".gif"
    if blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def sniff_name(blob: bytes) -> str:
    names = {".png": "PNG", ".jpg": "JPEG", ".gif": "GIF", ".webp": "WEBP", ".bin": "unknown"}
    return names[sniff_extension(blob)]


def debug_xml(root: ET.Element) -> None:
    print("\n--- XML structure (first 5 levels) ---")

    def walk(el: ET.Element, depth: int = 0) -> None:
        if depth > 5:
            return
        attrs = " ".join(f'{k}="{v[:40]}{"..." if len(v) > 40 else ""}"' for k, v in el.attrib.items())
        text_preview = ""
        if el.text and el.text.strip():
            t = el.text.strip()
            text_preview = f'  text="{t[:60]}{"..." if len(t) > 60 else ""}"'
        print("  " * depth + f"<{el.tag}{(' ' + attrs) if attrs else ''}>{text_preview}")
        for child in el:
            walk(child, depth + 1)

    walk(root)
    print()


def find_thumbnail_elements(root: ET.Element) -> list[ET.Element]:
    return list(root.iter("Thumbnail"))


def try_extract(root: ET.Element, debug: bool) -> tuple[bytes | None, str]:
    """Try all known ways to find base64 thumbnail data. Returns (blob, source_description)."""
    thumbs = find_thumbnail_elements(root)

    if not thumbs:
        return None, "No <Thumbnail> element found anywhere in the XML."

    if debug:
        print(f"Found {len(thumbs)} <Thumbnail> element(s).")

    for i, thumb in enumerate(thumbs):
        label = f"<Thumbnail>[{i}]"
        if debug:
            print(f"\n  {label} attributes: {dict(thumb.attrib)}")
            if thumb.text:
                preview = thumb.text.strip()[:80]
                print(f"  {label} text (first 80 chars): {preview!r}")

        # Try Source attribute
        b64 = (thumb.attrib.get("Source") or "").strip()
        if b64:
            if debug:
                print(f"  -> Found data in Source attribute ({len(b64)} chars)")
            blob, err = decode_b64(b64, debug)
            if blob is not None:
                return blob, f"Source attribute on {label}"
            if debug:
                print(f"  -> Decode failed: {err}")

        # Try element text
        if thumb.text and thumb.text.strip():
            b64 = thumb.text.strip()
            if debug:
                print(f"  -> Found data in element text ({len(b64)} chars)")
            blob, err = decode_b64(b64, debug)
            if blob is not None:
                return blob, f"text content of {label}"
            if debug:
                print(f"  -> Decode failed: {err}")

        # Try child <Source> element
        src = thumb.find("Source")
        if src is not None and src.text and src.text.strip():
            b64 = src.text.strip()
            if debug:
                print(f"  -> Found data in child <Source> element ({len(b64)} chars)")
            blob, err = decode_b64(b64, debug)
            if blob is not None:
                return blob, f"child <Source> of {label}"
            if debug:
                print(f"  -> Decode failed: {err}")

    return None, "Found <Thumbnail> element(s) but could not extract valid image data from any of them."


def decode_b64(data: str, debug: bool) -> tuple[bytes | None, str]:
    data = "".join(data.split())
    pad = (-len(data)) % 4
    if pad:
        data += "=" * pad
    try:
        blob = base64.b64decode(data, validate=True)
        return blob, ""
    except binascii.Error as e:
        # Try without validate in case of non-standard chars
        try:
            blob = base64.b64decode(data)
            if debug:
                print(f"  (decoded with validate=False; may have non-standard chars)")
            return blob, ""
        except Exception as e2:
            return None, str(e2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract thumbnail from a LightBurn .lbrn2/.lbrn file.")
    parser.add_argument("input", help="Path to .lbrn2 or .lbrn file")
    parser.add_argument("-o", "--output", default=None, help="Output path (default: <stem>_thumbnail.<ext> next to input)")
    parser.add_argument("--debug", action="store_true", help="Show detailed debug info about the XML structure")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}", file=sys.stderr)
        return 1
    if input_path.suffix.lower() not in (".lbrn2", ".lbrn"):
        print(f"WARNING: Unexpected extension {input_path.suffix!r} (expected .lbrn2 or .lbrn)", file=sys.stderr)

    print(f"Input:  {input_path}")
    print(f"Size:   {input_path.stat().st_size:,} bytes")

    # Parse XML
    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
        print(f"XML root tag: <{root.tag}>")
    except ET.ParseError as e:
        print(f"ERROR: Failed to parse XML: {e}", file=sys.stderr)
        return 1

    if args.debug:
        debug_xml(root)

    # Count elements for context
    all_tags = [el.tag for el in root.iter()]
    print(f"Total XML elements: {len(all_tags)}")
    thumb_count = all_tags.count("Thumbnail")
    print(f"<Thumbnail> elements: {thumb_count}")

    if thumb_count == 0:
        print("\nERROR: No <Thumbnail> element found in this file.")
        print("This file may not have a thumbnail, or the format is unexpected.")
        if args.debug:
            print("\nAll unique tags found:")
            for tag in sorted(set(all_tags)):
                print(f"  <{tag}>")
        return 1

    # Try to extract
    print("\nAttempting thumbnail extraction...")
    blob, source_desc = try_extract(root, debug=args.debug)

    if blob is None:
        print(f"\nERROR: {source_desc}")
        return 1

    ext = sniff_extension(blob)
    fmt = sniff_name(blob)
    print(f"Decoded {len(blob):,} bytes — detected format: {fmt}")
    print(f"Source: {source_desc}")

    if ext == ".bin":
        print(f"WARNING: First 16 bytes: {blob[:16].hex()}")
        print("This doesn't look like a recognized image format.")

    # Determine output path
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        out_path = input_path.with_name(f"{input_path.stem}_thumbnail{ext}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    print(f"\nSaved:  {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
