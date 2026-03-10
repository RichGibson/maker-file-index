# So you want to improve the code

This guide covers everything you need to work on `maker-file-index` — project layout, development workflow, running tests, and getting changes into the repo.

---

## Prerequisites

All development uses the `drinkbotos` conda environment. Make sure it's active or prefix commands with `conda run -n drinkbotos`.

```bash
conda activate drinkbotos
```

---

## Project layout

```
maker-file-index/
├── src/
│   └── maker_file_index/
│       ├── cli.py              # Entry point — main(), _run_once(), watch mode
│       ├── indexer.py          # scan(), resolve_inputs(), group_by_directory()
│       ├── model.py            # IndexRecord dataclass
│       ├── thumbnails.py       # thumbnail_path_for(), thumbnail_is_fresh()
│       ├── cleanup.py          # cleanup_stale_output() — removes orphaned output
│       ├── plugins/            # One file per supported file type
│       │   ├── base.py         # FilePlugin protocol
│       │   ├── lightburn.py    # .lbrn2 / .lbrn
│       │   ├── stl.py          # .stl
│       │   ├── dxf.py          # .dxf
│       │   ├── svg.py          # .svg
│       │   ├── scad.py         # .scad
│       │   ├── three_mf.py     # .3mf
│       │   ├── cdr.py          # .cdr
│       │   └── loader.py       # Loads plugins via entry points
│       ├── renderers/
│       │   ├── html.py         # All HTML output
│       │   └── markdown.py     # All Markdown output
│       └── templates/          # Jinja2 templates (.html.j2 and .md.j2)
│           ├── landing.html.j2
│           ├── dir_index.html.j2 / dir_index.md.j2
│           ├── report.md.j2
│           └── <type>_detail.html.j2 / <type>_detail.md.j2  (one pair per file type)
│
├── src/laser_tools/            # Standalone CLI tools (not part of the indexer)
│   └── lightburn/
│       ├── extract_notes.py    # lightburn-extract-notes command
│       └── extract_text.py     # lightburn-extract-text command
│
├── tests/                      # pytest test suite
│   ├── conftest.py             # Shared fixtures (file paths, DXF generator)
│   ├── test_plugins.py         # extract_* functions for all 7 file types
│   ├── test_thumbnails.py      # thumbnail_path_for(), thumbnail_is_fresh()
│   ├── test_cleanup.py         # cleanup_stale_output()
│   └── test_cli.py             # CLI smoke tests
│
├── files/                      # Sample files used as test fixtures
│   ├── shelf.lbrn2
│   ├── testfile.stl
│   ├── princess_donut.stl
│   ├── princess_donut.3mf
│   ├── octopus.svg
│   ├── live_laugh.cdr
│   └── sample.scad
│
├── scripts/                    # Standalone exploratory scripts — not installed
├── .github/workflows/
│   ├── test.yml                # Runs pytest on every push / PR
│   └── build.yml               # Builds macOS and Windows executables on version tags
├── pyproject.toml              # Package config, dependencies, entry points
└── CLAUDE.md                   # Instructions for Claude Code (AI assistant)
```

---

## Install for development

```bash
# From the repo root — installs the package in editable mode
conda run -n drinkbotos pip install -e .
```

You only need to reinstall when you change `pyproject.toml` (entry points, dependencies). Editing Python files takes effect immediately.

### If something feels broken

```bash
conda run -n drinkbotos pip uninstall maker-file-index
conda run -n drinkbotos pip install -e .
```

---

## Running the tool

```bash
# Against the sample files (quickest sanity check)
conda run -n drinkbotos maker-file-index files/

# Against any directory
conda run -n drinkbotos maker-file-index /path/to/files/

# Custom output location
conda run -n drinkbotos maker-file-index /path/to/files/ --output-dir /my/output/

# Watch for changes and rebuild automatically
conda run -n drinkbotos maker-file-index files/ --watch

# Without installing (dev mode)
conda run -n drinkbotos python -m maker_file_index.cli files/

# Show which plugin handles each file
conda run -n drinkbotos maker-file-index files/ --debug-plugins
```

Output goes to `maker_file_data/` by default (never touches your source files).

---

## Running tests

```bash
# Run all tests
conda run -n drinkbotos python -m pytest tests/

# Verbose — see each test name
conda run -n drinkbotos python -m pytest tests/ -v

# Just one test file
conda run -n drinkbotos python -m pytest tests/test_plugins.py

# Just one test
conda run -n drinkbotos python -m pytest tests/test_plugins.py::test_stl_returns_no_error

# Stop on first failure
conda run -n drinkbotos python -m pytest tests/ -x

# Quiet summary only
conda run -n drinkbotos python -m pytest tests/ -q
```

Tests run automatically on GitHub Actions for every push and pull request to `main`.

---

## Adding a new file type

1. Create `src/maker_file_index/plugins/yourtype.py` with a class implementing `can_handle()` and `index()`. Follow an existing plugin (e.g. `dxf.py`) as the template.
2. Add an `extract_yourtype_details()` function in the same file.
3. Register it in `pyproject.toml` under `[project.entry-points."maker_file_index.plugins"]`.
4. Reinstall: `pip install -e .`
5. Add templates: `yourtype_detail.html.j2` and `yourtype_detail.md.j2` in `templates/`.
6. Wire up rendering in `renderers/html.py` and `renderers/markdown.py` (follow the CDR pattern — it's the simplest).
7. Add a fixture file to `files/` and write tests in `tests/test_plugins.py`.

### Plugin entry point convention

```toml
[project.entry-points."maker_file_index.plugins"]
yourtype = "maker_file_index.plugins.yourtype:YourTypePlugin"
```

### Plugin attributes set before `index()` is called

```python
plugin.scan_root  # root directory of the scan
plugin.thumb_root  # output_dir/dirs/ — pass to thumbnail_path_for()
```

### Checking plugin loading

```python
from maker_file_index.plugins.loader import load_plugins
print([p.name for p in load_plugins()])
```

---

## Templates

Templates are Jinja2. Autoescape is enabled for `.html`/`.xml` only — not for `.md`.

- Change a template → just run the tool, no reinstall needed.
- HTML templates use `url_path()` for any path that goes into an `href` or `src`.
- Both renderers use `_relpath()` instead of `os.path.relpath()` directly — this normalizes path separators to forward slashes so links work on Windows.

---

## Triggering a release

Releases are built automatically when you push a version tag. The build workflow produces macOS and Windows executables and attaches them to the GitHub Release.

```bash
# Bump the version in pyproject.toml first, then:
git tag v0.1.3
git push origin v0.1.3
```

You can also trigger a build manually from the Actions tab without publishing.

---

## Commit convention

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

Examples:
```
feat: add watch mode for live rebuild on file changes
fix: normalize path separators to forward slashes on Windows
docs: rewrite README_dev as contributor guide
```

---

## Useful one-liners

```bash
# See recent commits
git log --oneline

# Check what plugins are loaded
conda run -n drinkbotos python -c "
from maker_file_index.plugins.loader import load_plugins
print([p.name for p in load_plugins()])
"

# Run against your actual files directory
conda run -n drinkbotos maker-file-index ~/Documents/LaserFiles/ --watch
```
