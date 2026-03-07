# maker-file-index

## File navigator for Maker files. Lightburn, STL, DXFs, etc.

Programmers have figured out that version control matters. They don't have files like 'project_final.doc', 'project_final_2.doc', 'project_final_really.doc.'

Version control, and project/file name management matter in other fields.

I can't speak for all 'Makers,' but I know that my code repositories tend
to be (reasonably) tidy, and my 3d printer, Laser Cutter, CNC Router, and other files
tend to not reflect the learnings that I made in my software.

This is a navigator for our design/machine control files. Run it and you can get an 
index of all of the supported files, along with thumbnails and whatever metadata that
I can pull out about that file.

![List view of Maker-file-index](docs/maker-file-index.png)

There is a list view, complete with the ability to choose dark mode, and to sort 
on name or recent file access. You can hide or show the sidebar, and generally
navigate around your files in convenient ways.

![Detail view of Maker-file-index](docs/maker-file-index-detail.png)

If you drill down to a file you get a detail view. Right now this works for Lightburn
files. Support for other formats hopefully to come!

## Features

- Plugin-based architecture — easy to extend with new file types
- **LightBurn** (`.lbrn2`, `.lbrn`) — embedded thumbnail and notes extraction
- **STL** — thumbnail generation via numpy-stl + matplotlib
- **OpenSCAD** (`.scad`) — thumbnail generation via OpenSCAD CLI
- **3MF** — embedded preview image extraction
- **SVG** — displayed directly as preview
- **DXF** — thumbnail generation via ezdxf + matplotlib
- **Corel Draw** (`.cdr`) — embedded thumbnail 

### HTML output

- Landing page with all top-level directories, sorted newest first
- Per-directory pages with thumbnail grid
- Sidebar with full directory tree navigation, current page highlighted, scroll position preserved
- Clickable file type stat buttons on landing page (show count, filter on click)
- File type filter buttons in sidebar on directory pages
- Text search box to filter cards by name
- Breadcrumb navigation
- Colored file type badges on every card
- Notes snippet displayed on file cards
- Error badge on cards where thumbnail generation failed
- **LightBurn detail pages** — clicking a `.lbrn2`/`.lbrn` file opens a rich detail page showing: thumbnail, file metadata (machine, LightBurn version, material height, size, modified date), notes, laser layer table (speed, power, passes, type), shape summary, and embedded text content

## Requirements

- Python 3.9+
- `numpy-stl`, `matplotlib`, `ezdxf` (installed automatically)
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

### extract_thumbnail

Standalone script for extracting and debugging thumbnails from LightBurn files.

```bash
python scripts/extract_thumbnail.py file.lbrn2
python scripts/extract_thumbnail.py file.lbrn2 -o thumb.png
python scripts/extract_thumbnail.py file.lbrn2 --debug
```

**Options:**

| Option | Description |
|--------|-------------|
| `file` | Path to `.lbrn2` or `.lbrn` file |
| `-o, --output PATH` | Output path (default: `<stem>_thumbnail.<ext>` next to input) |
| `--debug` | Show XML structure, where base64 data was found, decoded size, and detected image format |

The `--debug` flag is useful when a file has a `Thumbnail Source` in the XML but no image is being generated — it shows exactly what was found and where extraction failed.

## Supported file types

| Type | Extensions | Thumbnail |
|------|-----------|-----------|
| LightBurn | `.lbrn2`, `.lbrn` | Embedded in file |
| STL | `.stl` | Rendered via numpy-stl + matplotlib |
| OpenSCAD | `.scad` | Rendered via OpenSCAD CLI |
| 3MF | `.3mf` | Extracted from zip archive |
| SVG | `.svg` | Displayed directly |
| DXF | `.dxf` | Rendered via ezdxf + matplotlib |
| Corel Draw | `.cdr` | Embedded in file |
