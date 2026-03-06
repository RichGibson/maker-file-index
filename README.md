# maker-file-index

Index maker project files and generate a Markdown and HTML catalog with thumbnails and notes.

## Features

- Plugin-based architecture — easy to extend with new file types
- **LightBurn** (`.lbrn2`, `.lbrn`) — thumbnails and notes extraction
- **STL** — thumbnail generation via numpy-stl + matplotlib
- **SCAD** — thumbnail generation via OpenSCAD CLI (requires `openscad` installed)
- **DXF, SVG, 3MF** — file detection and indexing
- Recursive directory scanning
- Markdown report output
- HTML directory pages with thumbnail grid and sidebar tree navigation

## Requirements

- Python 3.9+
- `numpy-stl`, `matplotlib` (installed automatically)
- `openscad` (optional, for SCAD thumbnails — install separately)

## Quick start

```bash
pip install -e .
maker-file-index <path>
```

## Usage

```bash
maker-file-index TARGET [options]
```

Generates a Markdown report and per-directory HTML pages with thumbnails.

## Arguments

### `TARGET`

File, directory, or glob to scan.

## Options

### `-o, --output PATH`

Output Markdown filename.
Default: `lightburn_notes.md`

### `--no-recursive`

Do not scan subdirectories.

### `--relpath-root PATH`

Make file paths in the report relative to this directory.

### `--debug-plugins`

Show which plugin handles each file (useful for debugging).

## Utilities

### Extract Notes

```bash
lightburn-extract-notes <filename>
```

Reads a LightBurn file and extracts the notes.

### Extract Text

```bash
lightburn-extract-text <filename>
```

Reads a LightBurn file and extracts the text.

## Status

Working prototype.

Currently supports:
- LightBurn (`.lbrn2`) — thumbnails and notes
- STL — thumbnail generation
- SCAD — thumbnail generation (requires OpenSCAD)
- DXF, SVG, 3MF — file detection
