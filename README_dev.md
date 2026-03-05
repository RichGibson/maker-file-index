# dev README - my ugly work in progress notes.

## next

make the tree highlight the current directory, like:

christmas
├── E638 Layered Christmas Set
│   ├── DXF
│   ├── PNG
│   └── SVG
└── tea_light   ← highlighted

One top-level HTML landing page that shows:

• newest projects
• directories with thumbnails
• summary stats
• search/filter


## Git

Git Messages 

<type>: short summary

optional longer explanation

| Type       | Meaning                             | Example                                                  |
| ---------- | ----------------------------------- | -------------------------------------------------------- |
| `feat`     | new feature                         | `feat: add directory index pages`                        |
| `fix`      | bug fix                             | `fix: correct README path generation`                    |
| `refactor` | internal change, no behavior change | `refactor: remove LightBurnInfo in favor of IndexRecord` |
| `docs`     | documentation                       | `docs: add CLI usage section to README`                  |
| `chore`    | maintenance                         | `chore: add gitignore and project structure`             |
| `perf`     | performance improvement             | `perf: avoid re-reading thumbnails`                      |


git log --oneline


in developement
PYTHONPATH=src python -m maker_file_index.cli ../.

install 

pip uninstall maker-file-index

in maker-file-index
python -m pip install -e .

which maker-file-index

run it.
maker-file-index  ../.


normal development
in maker-file-index

python -m pip install -e .

test
maker-file-index --help
maker-file-index ../. --debug-plugins


python - <<'PY'
from maker_file_index.plugins.loader import load_plugins
print([p.name for p in load_plugins()])
PY
....

🧠 Pro tip (you’ll thank yourself later)

During active development, this is your muscle memory:

change Python → just run

change pyproject entry points → reinstall editable

something feels cursed → uninstall + reinstall

...
## dev log


Sat Feb 28 14:59:59 PST 2026
- moved to template driven.

Next(ish) break down by directory

-possible editor for notes
