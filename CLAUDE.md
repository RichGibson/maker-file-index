# maker-file-index

A Python CLI tool that indexes maker files (LightBurn, STL, SCAD, DXF, SVG, 3MF, CDR) with thumbnails and notes, generating HTML and Markdown reports organized by directory. All output goes into a dedicated `maker_file_data/` directory — source files are never modified.

## Project Structure

```
src/
  maker_file_index/
    cli.py              # Entry point: main()
    indexer.py          # File scanning / scan() / resolve_inputs()
    model.py            # IndexRecord dataclass
    thumbnails.py       # thumbnail_path_for(), thumbnail_is_fresh()
    cleanup.py          # cleanup_stale_output() — removes orphaned output files
    plugins/            # File-type plugins (plugin architecture)
      base.py           # FilePlugin Protocol
      lightburn.py      # .lbrn2 / .lbrn — thumbnail, notes, layers, time estimate
      stl.py            # .stl — thumbnail via numpy-stl + matplotlib
      scad.py           # .scad — thumbnail via OpenSCAD CLI (optional)
      dxf.py            # .dxf — thumbnail via ezdxf + matplotlib
      svg.py            # .svg — source file used directly as preview
      three_mf.py       # .3mf — embedded preview extraction
      cdr.py            # .cdr — embedded BMP thumbnail extraction
      loader.py         # Entry-point plugin loader
    renderers/
      html.py           # HTML landing page, directory pages, detail pages
      markdown.py       # Markdown report, directory pages, detail pages
    templates/          # Jinja2 templates (.html.j2 and .md.j2)
      landing.html.j2
      dir_index.html.j2
      dir_index.md.j2
      report.md.j2
      lightburn_detail.html.j2  lightburn_detail.md.j2
      stl_detail.html.j2        stl_detail.md.j2
      three_mf_detail.html.j2   three_mf_detail.md.j2
      svg_detail.html.j2        svg_detail.md.j2
      dxf_detail.html.j2        dxf_detail.md.j2
      scad_detail.html.j2       scad_detail.md.j2
      cdr_detail.html.j2        cdr_detail.md.j2
  laser_tools/          # Standalone laser utilities
    lightburn/
      extract_notes.py  # CLI: lightburn-extract-notes
      extract_text.py   # CLI: lightburn-extract-text
scripts/                # Exploratory / standalone scripts (not installed)
  lightburn_extract.py  scad_extract.py   stl_extract.py
  3mf_extract.py        svg_extract.py    dxf_extract.py
  extract_thumbnail.py
files/                  # Sample/test maker files (shelf.lbrn2, testfile.stl, testfile.scad)
```

## Output Structure

Running `maker-file-index /path/to/files/` produces:

```
maker_file_data/
  maker_file_notes.md       # Markdown summary report
  index.html                # HTML landing page
  dirs/
    <subdir>/
      index.html            # Directory listing (HTML)
      index.md              # Directory listing (Markdown)
      <file>.html           # Detail page (HTML)
      <file>.md             # Detail page (Markdown)
      <file>_thumbnail.png  # Generated thumbnail
```

## Install & Run

```bash
# Install editable (run from repo root)
conda run -n drinkbotos pip install -e .

# Run
conda run -n drinkbotos maker-file-index /path/to/files/
conda run -n drinkbotos maker-file-index /path/to/files/ --output-dir /my/output/
conda run -n drinkbotos maker-file-index /path/to/files/ --alongside-source  # old behavior
conda run -n drinkbotos maker-file-index /path/to/files/ --debug-plugins
conda run -n drinkbotos maker-file-index --version
conda run -n drinkbotos maker-file-index --help

# Test against sample files
conda run -n drinkbotos maker-file-index files/

# Dev (no install)
conda run -n drinkbotos python -m maker_file_index.cli /path/to/files/

# Other CLI tools
conda run -n drinkbotos lightburn-extract-notes /path/to/file.lbrn2
conda run -n drinkbotos lightburn-extract-text /path/to/file.lbrn2
```

## Key CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output-dir` | `maker_file_data` | Output directory for all generated files |
| `--alongside-source` | off | Write everything into the source directory tree (old behavior, modifies source dir) |
| `--no-recursive` | off | Do not scan subdirectories |
| `--debug-plugins` | off | Show which plugin handles each file |
| `--version` | — | Print version and exit |

## Plugin System

Plugins are registered via `pyproject.toml` entry points under `maker_file_index.plugins`. Each plugin implements `can_handle(path)` and `index(path) -> IndexRecord`.

Two attributes are set on each plugin before `index()` is called:
- `plugin.scan_root` — root directory of the scan (for relative path display)
- `plugin.thumb_root` — `output_dir/dirs/` when using a dedicated output dir, `None` when `--alongside-source`

`thumbnail_path_for(source, thumb_root=, scan_root=)` uses these to place thumbnails either in the output dir tree or alongside the source file.

After adding or changing entry points, reinstall: `conda run -n drinkbotos pip install -e .`

To debug plugin loading:
```python
from maker_file_index.plugins.loader import load_plugins
print([p.name for p in load_plugins()])
```

## Development Tips

- Change Python code → just run (no reinstall needed in editable mode)
- Change `pyproject.toml` entry points → reinstall
- Something feels broken → `conda run -n drinkbotos pip uninstall maker-file-index && pip install -e .`
- Test files are in `files/` — run `maker-file-index files/` for a quick sanity check
- Templates are Jinja2; autoescape is enabled for `.html`/`.xml` only, not `.md`
- Stale output (orphaned HTML/MD/thumbnails) is cleaned up automatically on each run

## Conda Environment

All development uses the `drinkbotos` conda environment. `numpy-stl`, `matplotlib`, and `ezdxf` are installed there. OpenSCAD thumbnail generation requires the `openscad` binary on PATH.

## Commit Convention

```
<type>: short summary
```

| Type | Meaning |
|------|---------|
| `feat` | new feature |
| `fix` | bug fix |
| `refactor` | internal change, no behavior change |
| `docs` | documentation |
| `chore` | maintenance |
| `perf` | performance improvement |
