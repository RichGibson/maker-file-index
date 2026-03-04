#!/usr/bin/env python3

import sys
import xml.etree.ElementTree as ET
import html
import pdb
import argparse



def extract_notes(filename: str) -> str | None:
    """
    Extract the Notes field from a LightBurn .lbrn2 file.

    Returns:
        The decoded notes string, or None if not found.
    """
    tree = ET.parse(filename)
    root = tree.getroot()

    notes_elem = root.find(".//Notes")
    if notes_elem is None:
        return None

    raw_notes = notes_elem.attrib.get("Notes", "")
    decoded_notes = html.unescape(raw_notes)

    return decoded_notes




def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lightburn-extract-notes")
    parser.add_argument("filename")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    print(args.filename)
    pdb.set_trace()
    notes = extract_notes(args.filename)
    if notes is None:
        print("No notes found.")
        return 1

    print(notes)
    return 0

if __name__ == "__main__":
    main()
