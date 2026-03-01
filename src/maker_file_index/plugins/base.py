from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol



@dataclass(frozen=True)
class IndexRecord:
    """ When you change this, you also need to change it in the plugin's index method"""
    path: Path
    directory: Path
    notes: str = ""
    thumbnail_path: Path = Path("")
    error: str = ""


class FilePlugin(Protocol):
    """
    A plugin knows how to:
    - decide if it can handle a file
    - extract metadata (notes, etc.)
    - extract a thumbnail (optional)
    """
    name: str

    def can_handle(self, path: Path) -> bool: ...
    def index(self, path: Path) -> IndexRecord: ...
