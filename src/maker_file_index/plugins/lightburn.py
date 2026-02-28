from __future__ import annotations

import base64
import binascii
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


LIKELY_EXTS = {".lbrn2", ".lbrn"}


@dataclass(frozen=True)
class LightBurnInfo:
    path: Path
    notes: str
    thumbnail_path: Path = Path("")
    error: str = ""


def is_likely_lightburn_project(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in LIKELY_EXTS


def _find_thumbnail_b64(root: ET.Element) -> str:
    for thumb in root.iter("Thumbnail"):
        b64 = (thumb.attrib.get("Source") or "").strip()
        if b64:
            return b64

        if thumb.text and thumb.text.strip():
            return thumb.text.strip()

        src = thumb.find("Source")
        if src is not None and src.text and src.text.strip():
            return src.text.strip()

    raise ValueError("No thumbnail found. Expected a <Thumbnail> element with base64 data.")


def _decode_b64(data_b64: str) -> bytes:
    data_b64 = "".join(data_b64.split())
    pad = (-len(data_b64)) % 4
    if pad:
        data_b64 += "=" * pad
    try:
        return base64.b64decode(data_b64, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Thumbnail base64 decode failed: {e}") from e


def _sniff_extension(blob: bytes) -> str:
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
    tree = ET.parse(input_path)
    root = tree.getroot()

    b64 = _find_thumbnail_b64(root)
    blob = _decode_b64(b64)

    if output_path is None:
        ext = _sniff_extension(blob)
        output_path = input_path.with_name(f"{input_path.stem}_thumbnail{ext}")

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {output_path} (use overwrite=True)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(blob)
    return output_path


def extract_notes_and_thumbnail(path: Path, *, overwrite_thumbnail: bool = True) -> LightBurnInfo:
    """
    Returns Notes (blank if missing) and writes/returns the extracted thumbnail path if present.
    Supports:
      <Notes>text</Notes>
      <Notes Notes="text with &#10; newlines" />
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        notes_el = root.find(".//Notes")
        notes_text = ""
        if notes_el is not None:
            attr_val = (notes_el.attrib.get("Notes") or "").strip()
            if attr_val:
                notes_text = attr_val
            else:
                notes_text = (notes_el.text or "").strip()

        notes_text = notes_text.replace("\r\n", "\n").replace("\r", "\n").strip()

        thumb_path = Path("")
        try:
            # thumbnail is optional; if missing, we keep blank
            thumb_path = extract_thumbnail(path, overwrite=overwrite_thumbnail)
        except Exception:
            thumb_path = Path("")

        return LightBurnInfo(path=path, notes=notes_text, thumbnail_path=thumb_path)

    except ET.ParseError as e:
        return LightBurnInfo(path=path, notes="", thumbnail_path=Path(""), error=f"XML parse error: {e}")
    except Exception as e:
        return LightBurnInfo(path=path, notes="", thumbnail_path=Path(""), error=f"{type(e).__name__}: {e}")

from maker_file_index.plugins.base import FilePlugin, IndexRecord

class LightBurnPlugin:
    name = "lightburn"

    def can_handle(self, path: Path) -> bool:
        return is_likely_lightburn_project(path)

    def index(self, path: Path) -> IndexRecord:
        info = extract_notes_and_thumbnail(path, overwrite_thumbnail=True)
        return IndexRecord(
            path=info.path,
            notes=info.notes,
            thumbnail_path=info.thumbnail_path,
            error=info.error,
        )
