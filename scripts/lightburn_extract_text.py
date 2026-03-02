#!/usr/bin/env python3

import argparse
import html
import sys
import xml.etree.ElementTree as ET
import pdb


def lightburn_extract_text(filename: str) -> list[str]:
    """
    Extract all text strings from a LightBurn .lbrn2 (XML) file.

    LightBurn stores text shapes like:
      <Shape Type="Text" ... Str="Side" ...>

    Returns:
        A list of decoded strings (in document order). Empty strings are omitted.
    """
    tree = ET.parse(filename)
    root = tree.getroot()

    out: list[str] = []
    for shape in root.findall(".//Shape"):
        if shape.attrib.get("Type") != "Text":
            continue

        raw = shape.attrib.get("Str", "")
        s = html.unescape(raw).strip()
        if s:
            out.append(s)

    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="lightburn_extract_text",
        description="Extract text (Shape Type='Text' Str='...') from a LightBurn .lbrn2 file.",
    )
    parser.add_argument("filename", help="Path to a .lbrn2 LightBurn file")
    args = parser.parse_args(argv)

    strings = lightburn_extract_text(args.filename)
    for s in strings:
        print(s)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
