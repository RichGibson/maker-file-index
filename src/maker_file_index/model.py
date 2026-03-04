from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexRecord:
    """ When you change this, you also need to change it in the plugin's index method"""
    path: Path
    directory: Path
    notes: str = ""
    thumbnail_path: Path = Path("")
    error: str = ""
