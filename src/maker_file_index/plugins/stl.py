from __future__ import annotations

import os
from pathlib import Path

from maker_file_index.model import IndexRecord
from maker_file_index.thumbnails import thumbnail_path_for, thumbnail_is_fresh
from urllib.parse import quote
import pdb

def url_path(p: str) -> str:
    """
    Convert a filesystem-relative path to a browser-friendly URL path.
    Encodes spaces and special chars, keeps / separators.
    """
    p=str(p)
    return quote(p.replace(os.sep, "/"), safe="/")

class STLPlugin:
    name = "stl"

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".stl"

    def find_sidecar_image(self, stl_path: Path) -> Path:
        """
        Look for an existing preview image for this STL.
        Search order:
          1) same directory as STL
          2) ./files
          3) ./images

        Matches same stem: foo.stl -> foo.png/jpg/jpeg/webp
        """
        exts = (".png", ".jpg", ".jpeg", ".webp")
        roots = [stl_path.parent, stl_path.parent / "files", stl_path.parent / "images"]

        candidates: list[Path] = []
        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            print()
            for ext in exts:
                p = root / f"{stl_path.stem}{ext}"
                if p.exists() and p.is_file():
                    candidates.append(p)
                else:
                    p = root / f"{stl_path.stem}_thumbnail{ext}"
                    n=url_path(p)
                    if p.exists() and p.is_file():
                        candidates.append(p)

        if not candidates:
            # Fallback: use any image file in the STL directory, or ./files, or ./images
            any_images: list[Path] = []
            for root in roots:
                print(f'root {root}')
                if not root.exists() or not root.is_dir():
                    continue
                for ext in exts:
                    print(f'ext {ext}')
                    any_images.extend(root.glob(f"*{ext}"))

            any_images = [p for p in any_images if p.is_file()]
            #print(any_images)
            #pdb.set_trace()
            if not any_images:
                return Path("")

            any_images.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return any_images[0]

        # Prefer the newest image if multiple exist
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def render_thumbnail(self, path: Path, thumb_path: Path) -> str:
        import subprocess

        proc = subprocess.run(
            [
                "openscad",
                "-o", str(thumb_path),
                "--imgsize=400,400",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # Return stderr text if it didn't produce a file
        if not thumb_path.exists():
            #print(proc.stderr or proc.stdout or "")
            #pdb.set_trace()
            return (proc.stderr or proc.stdout or "").strip()

        return ""

    def index(self, path: Path) -> IndexRecord:
        thumb_path = thumbnail_path_for(path)
        sidecar = self.find_sidecar_image(path)
        print(path,sidecar)

        if sidecar:
            return IndexRecord(
                path=path,
                directory=path.parent,
                notes="",
                thumbnail_path=sidecar.resolve(),
                error="",
            )
        else:
            print(f'no sidecar for {path}')
            pdb.set_trace()

