#!/usr/bin/env python3

import sys
import xml.etree.ElementTree as ET
import html
import pdb


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


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file.lbrn2>")
        sys.exit(1)

    filename = sys.argv[1]
    notes = extract_notes(filename)

    if notes is None:
        print("No notes found.")
    else:
        print(notes)

if __name__ == "__main__":
    main()
