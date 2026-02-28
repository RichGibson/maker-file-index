# maker-file-index

Index maker project files (starting with LightBurn) and generate a Markdown catalog with thumbnails and notes.

## Features

- Plugin-based architecture
- LightBurn support (notes + thumbnails)
- STL and SCAD detection (thumbnail TBD)
- Recursive directory scanning
- Markdown report output

## Quick start

```bash
python -m pip install -e .
maker-file-index <path> --debug-plugins
```

## Usage

```bash
maker-file-index TARGET [options]

## Arguments

### TARGET

File, directory, or glob to scan.

## Options

### `-o, --output PATH`

Output Markdown filename.
Default: lightburn_notes.md

### `--no-recursive`

Do not scan subdirectories.

### `--relpath-root PATH`

Make file paths in the report relative to this directory.

### `--debug-plugins`

Show which plugin handles each file (useful for debugging).

## Status

Working prototype.

Currently supports:
- LightBurn (.lbrn2) thumbnails and notes
- STL and SCAD file detection

Planned:
- STL thumbnail generation
- More file-type plugins
- HTML/web viewer
