# maker-file-index

Index maker project files and generate a Markdown and HTML catalog with thumbnails and notes.

## Features

- Plugin-based architecture — easy to extend with new file types
- **LightBurn** (`.lbrn2`, `.lbrn`) — embedded thumbnail and notes extraction
- **STL** — thumbnail generation via numpy-stl + matplotlib
- **OpenSCAD** (`.scad`) — thumbnail generation via OpenSCAD CLI
- **3MF** — embedded preview image extraction
- **SVG** — displayed directly as preview
- **DXF** — file detection and indexing

### HTML output

- Landing page with all top-level directories, sorted newest first
- Per-directory pages with thumbnail grid
- Sidebar with full directory tree navigation and current page highlighted
- File type filter buttons (LightBurn, STL, OpenSCAD, 3MF, SVG, DXF)
- Text search box to filter cards by name
- Breadcrumb navigation
- Colored file type badges on every card
- Notes snippet displayed on file cards
- Error badge on cards where thumbnail generation failed

## Requirements

- Python 3.9+
- `numpy-stl`, `matplotlib` (installed automatically)
- `openscad` (optional, for OpenSCAD thumbnails — install separately)

## Quick start

```bash
pip install -e .
maker-file-index <path>
```

Generates:
- `lightburn_notes.md` — Markdown report
- `index.html` — landing page
- `dirs/` — per-directory HTML pages

## Usage

```bash
maker-file-index TARGET [options]
```

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

Show which plugin handles each file.

## Utilities

```bash
lightburn-extract-notes <filename>   # Extract notes from a LightBurn file
lightburn-extract-text <filename>    # Extract text from a LightBurn file
```

## Supported file types

| Type | Extensions | Thumbnail |
|------|-----------|-----------|
| LightBurn | `.lbrn2`, `.lbrn` | Embedded in file |
| STL | `.stl` | Rendered via numpy-stl + matplotlib |
| OpenSCAD | `.scad` | Rendered via OpenSCAD CLI |
| 3MF | `.3mf` | Extracted from zip archive |
| SVG | `.svg` | Displayed directly |
| DXF | `.dxf` | None |
