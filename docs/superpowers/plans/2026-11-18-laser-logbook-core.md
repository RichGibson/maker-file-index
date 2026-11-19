# Laser Logbook Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `laser-log build` command that decodes LightBurn jobs, stores their settings permanently, and writes one Markdown page per day into `~/projects/laserblog/files/log/` without ever losing hand-written notes.

**Architecture:** New package `maker_file_index.logbook` with small single-purpose modules: Ruida decoder, debug-log reader, jobs CSV reader, project-file layers (with git history), durable job store, day-page renderer, and a CLI. Pages are Jinja2 Markdown templates, like the rest of maker-file-index. The day page is regenerated freely, and notes blocks are carried over verbatim.

**Tech Stack:** Python 3 (conda env `drinkbotos`), stdlib `xml.etree`, `subprocess` for git, Jinja2 (already used), pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-laser-logbook.md`

**Follow-on plans (not this one):** plan 2, photo matching from `~/Downloads` with confirmation. Plan 3, `serve` notes web UI.

## Global Constraints

- Ruida magic `0x88`. Numbers: 5×7-bit big-endian. Speed µm/s ÷ 1000 = mm/s. Power `raw*100/0x3FFF`, rounded to 1 decimal.
- Day page path `log/YYYY-MM-DD.md`. Stored jobs `log/jobs/YYYY-MM-DD/HHMMSS.json`.
- Notes markers: `<!-- notes:start -->`/`<!-- notes:end -->` (day) and `<!-- notes:<id>:start -->`/`<!-- notes:<id>:end -->`, where `<id>` is `job-HHMMSS`.
- Generated pages carry the first line `<!-- generated-by: maker-file-index laser-log -->`. **Pages without it are never written.** `log/2026-11-18.md` is hand-made and must survive.
- Sessions split on gaps over 45 minutes.
- Source files are only read, never modified (project rule).
- No em-dashes in generated copy (user rule).
- Commits: `<type>: short summary` + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run tests with `conda run -n drinkbotos python -m pytest tests/logbook -q`.

## Review Focus

1. **A truncated stream** (the debug log is written in batches, so the last ` O: "` line can end mid-hex with no closing quote). Decode the complete bytes, set `truncated=True`, never raise. Test in Task 2.
2. **Midnight rollover** in the debug log (lines carry only `HH:MM:SS`). Timestamps after a backwards jump belong to the next day. Test in Task 2.
3. **Blank `Project` (unsaved) and paths that no longer exist** (45 in the real history). The page shows `(unsaved project)` / `file no longer at this path`, with no crash. Test in Task 6.
4. **Re-running build after LightBurn resets its log.** Already-stored job JSON is kept and not replaced by "not captured". Test in Task 5.
5. **Notes edited by hand, including a notes block whose job disappeared.** The text is preserved under `## Orphaned notes`, never dropped. Test in Task 6.

---

### Task 1: Ruida stream decoder

**Files:**
- Create: `src/maker_file_index/logbook/__init__.py` (empty), `src/maker_file_index/logbook/ruida.py`
- Test: `tests/logbook/__init__.py` (empty), `tests/logbook/test_ruida.py`

**Interfaces:**
- Produces:
  - `unswizzle(b: int, magic: int = 0x88) -> int`
  - `swizzle(b: int, magic: int = 0x88) -> int` (the inverse, so tests can build streams)
  - `@dataclass(frozen=True) class Setting: speed_mm_s: float; min_power: float; max_power: float`
  - `decode_settings(raw: bytes) -> list[Setting]`: distinct settings from the **body** commands, in first-seen order. Uses the header only for layers whose body entry is missing.
  - `grid(settings: list[Setting]) -> tuple[list[float], list[float]] | None`: (sorted speeds, sorted powers) when at least 3×3 settings with `min_power == max_power` cover every speed×power pair. Otherwise `None`.

- [ ] **Step 1: Write failing tests** in `tests/logbook/test_ruida.py`. Helpers in the test build plain command bytes, then swizzle them:
  - `test_swizzle_roundtrip`: `all(unswizzle(swizzle(b)) == b for b in range(256))`
  - `test_known_byte`: `unswizzle(0x89) == 0x88`. Real stream bytes `89` → move opcode; seen 147 times in the 2026-11-18 vector test.
  - `test_body_settings`: stream of `CA 02 00`, `C9 02 <14000 as n5>`, `C6 01 <28%>`, `C6 02 <28%>` → `[Setting(14.0, 28.0, 28.0)]`
  - `test_header_only_layer_used_when_no_body`: header `C9 04 05 <5000>`, `C6 31 05 <10%>`, `C6 32 05 <10%>` with no body → `[Setting(5.0, 10.0, 10.0)]`
  - `test_grid_detects_material_test`: the 6×6 from 2026-11-18 (speeds 5,14,23,32,41,50 × powers 10,28,46,64,82,100) plus `Setting(60, 15, 25)` → `([5,14,23,32,41,50], [10,28,46,64,82,100])`
  - `test_grid_none_for_project_job`: two settings → `None`
  - `test_garbage_does_not_raise`: `decode_settings(bytes(range(256)) * 4)` returns a list.
  - Encoding helpers in the test: `n5(v) = [(v >> s) & 0x7F for s in (28, 21, 14, 7, 0)]`, `p2(pct) = [(r >> 7) & 0x7F, r & 0x7F]` with `r = round(pct * 0x3FFF / 100)`.
- [ ] **Step 2: Run, expect FAIL** (module missing): `conda run -n drinkbotos python -m pytest tests/logbook/test_ruida.py -q`
- [ ] **Step 3: Implement `ruida.py`.** `unswizzle` per the spec. Scan byte by byte: match each command in the Global Constraints table, consume its length, otherwise advance 1. Body: track the current speed and powers, and record a `Setting` each time a `CA 02` layer select is followed by speed and both powers.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: add Ruida stream decoder for laser logbook`

### Task 2: Debug log reader

**Files:**
- Create: `src/maker_file_index/logbook/debuglog.py`
- Test: `tests/logbook/test_debuglog.py`

**Interfaces:**
- Consumes: nothing. Raw bytes are passed to `decode_settings` later (Task 5).
- Produces:
  - `@dataclass class StreamJob: started: datetime; raw: bytes; truncated: bool`
  - `read_stream_jobs(path: Path) -> list[StreamJob]`. The date comes from the first header line's `"Wed Nov 18 2026"`. A job starts at each `Protocol::GenerateCuts` line, and the hex comes from following ` O: "` lines.

- [ ] **Step 1: Write failing tests** using small log text written to `tmp_path`:
  - `test_two_jobs_split`: header + `20:45:45.124  D: Protocol::GenerateCuts time: 0` + 2 `O:` lines + `21:18:53.711 ... GenerateCuts` + 1 `O:` line → 2 jobs, `started == datetime(2026,11,18,20,45,45,124000)`, raw bytes equal the concatenated hex.
  - `test_truncated_last_line` (Review Focus 1): last line `21:18:53.800  D: O: "c40b0982077` (odd length, no closing quote) → `truncated is True`, and raw holds the complete byte pairs only.
  - `test_midnight_rollover` (Review Focus 2): GenerateCuts at `23:59:50.000`, then at `00:00:10.000` → second job dated 2026-11-19.
  - `test_missing_file_returns_empty`: nonexistent path → `[]`.
  - `test_noise_lines_ignored`: `EV: 1010 took 2272 uS` and `I: "d409..."` lines don't add bytes.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `read_stream_jobs`.** Read with `errors="replace"`. Only ` O: "` lines feed the hex.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: read job streams from LightBurn debug log`

### Task 3: Jobs CSV and sessions

**Files:**
- Create: `src/maker_file_index/logbook/jobs.py`
- Test: `tests/logbook/test_jobs.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Job: when: datetime; device: str; project: Path | None; sent_file: str`
  - `read_jobs(csv_path: Path) -> list[Job]` (a blank Project gives `project=None`)
  - `jobs_by_day(jobs: list[Job]) -> dict[date, list[Job]]`
  - `sessions(jobs: list[Job], gap: timedelta = timedelta(minutes=45)) -> list[list[Job]]`

- [ ] **Step 1: Write failing tests** with a CSV in `tmp_path` using the real header `Timestamp,Device,Project,Sent File`:
  - `test_blank_project_is_none`
  - `test_sent_file_kept`: row with `COASTERS` → `sent_file == "COASTERS"`
  - `test_sessions_split_on_45_min`: jobs at 19:16, 19:31, 20:18, 21:18 → `[[19:16, 19:31], [20:18], [21:18]]`. 47 and 60 minute gaps split; 15 doesn't.
  - `test_jobs_by_day`
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** with `csv.DictReader` and `datetime.fromisoformat`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: read LightBurn job history and group sessions`

### Task 4: Project layers with power, and file version at a time

**Files:**
- Modify: `src/maker_file_index/plugins/lightburn.py:280-357`. Add `max_power: float | None = None`, `min_power: float | None = None` to `_CutSetting` and fill them from `maxPower`/`minPower` in `_lb_parse_cut_settings`.
- Create: `src/maker_file_index/logbook/projectfile.py`
- Test: `tests/logbook/test_projectfile.py`

**Interfaces:**
- Consumes: `_lb_parse_cut_settings(root) -> dict[int, _CutSetting]` from `plugins/lightburn.py`
- Produces:
  - `@dataclass(frozen=True) class Layer: index: int; name: str; mode: str; speed: float | None; min_power: float | None; max_power: float | None; passes: int; shapes: int`. `mode` is the `CutSetting` `type` attribute (`Cut`/`Scan`). `shapes` counts `Shape` elements whose `CutIndex` equals `index`.
  - `layers_from_bytes(xml: bytes) -> list[Layer]`
  - `@dataclass(frozen=True) class FileVersion: source: str; layers: list[Layer]`. `source` is `"git <short-hash>"`, `"current file"`, or `"missing"`.
  - `version_at(project: Path, when: datetime) -> FileVersion`. Pick the newer of `git log -1 --before=<when> --format=%h -- <project>` and the same for `<stem>_backup.lbrn2`, then `git show <hash>:<relpath>`. Use `git -C <project.parent>`. If there's no repo or no commit, fall back to the current file. If the file is gone, return `missing` with `[]`.

- [ ] **Step 1: Write failing tests:**
  - `test_power_parsed`: inline XML with `<CutSetting type="Cut"><index Value="0"/><speed Value="14"/><maxPower Value="60"/><minPower Value="60"/></CutSetting>` → `Layer(index=0, mode="Cut", speed=14.0, max_power=60.0, min_power=60.0, ...)`
  - `test_shapes_counted`: tiny inline XML with 2 Shapes on `CutIndex="0"` → `shapes == 2`.
  - `test_version_at_uses_git` : `git init` in `tmp_path`, commit a v1 file at a fixed date (`GIT_COMMITTER_DATE`), commit a v2 later. `version_at(file, between)` returns v1's layers and `source.startswith("git ")`.
  - `test_version_at_prefers_newer_backup`: also commit `<stem>_backup.lbrn2` after v1 but before `when` → backup's layers.
  - `test_missing_file`: nonexistent path → `FileVersion("missing", [])`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Also run the existing suite to confirm the lightburn change broke nothing: `conda run -n drinkbotos python -m pytest tests/test_plugins.py -q`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: project layers with power and file version at job time`

### Task 5: Durable job store

**Files:**
- Create: `src/maker_file_index/logbook/store.py`
- Test: `tests/logbook/test_store.py`

**Interfaces:**
- Consumes: `Setting`, `decode_settings`, `grid` (Task 1). `StreamJob` (Task 2).
- Produces:
  - `save_stream_job(log_dir: Path, job: StreamJob) -> Path`. Writes `log/jobs/YYYY-MM-DD/HHMMSS.json` = `{"started": iso, "truncated": bool, "bytes": int, "settings": [{"speed_mm_s","min_power","max_power"}...]}`. A truncated job **never overwrites** a stored non-truncated one, and a longer stream replaces a shorter truncated one (the log fills in later).
  - `load_stored(log_dir: Path, day: date) -> dict[datetime, list[Setting]]`
  - `match_stream(job_time: datetime, stored: dict[datetime, list[Setting]], tolerance_s: float = 5.0) -> list[Setting] | None`. The CSV says 20:45:45 and the log says 20:45:45.124.

- [ ] **Step 1: Write failing tests:**
  - `test_save_and_load_roundtrip`
  - `test_log_reset_keeps_stored` (Review Focus 4): save a job, then run the store with an empty stream list. `load_stored` still returns it.
  - `test_longer_truncated_replaces_shorter`, `test_truncated_never_overwrites_complete`
  - `test_match_within_tolerance`: 20:45:45 matches the stored 20:45:45.124; 20:46:00 doesn't.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** with `json`, timestamp to millisecond in `started`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: store decoded job settings under log/jobs`

### Task 6: Day page renderer and notes preservation

**Files:**
- Create: `src/maker_file_index/logbook/daypage.py`, `src/maker_file_index/templates/log_day.md.j2`
- Test: `tests/logbook/test_daypage.py`

**Interfaces:**
- Consumes: `Job`, `sessions` (Task 3). `FileVersion`, `version_at` (Task 4). `match_stream`, `grid` (Tasks 1, 5).
- Produces:
  - `render_day(day: date, jobs: list[Job], stored: dict[datetime, list[Setting]], versions: Callable[[Path, datetime], FileVersion]) -> str`. Passing `versions` in keeps tests free of git.
  - `merge_notes(existing: str, generated: str) -> str`
  - `GENERATED_MARK = "<!-- generated-by: maker-file-index laser-log -->"`

Page layout, matching the hand-made `~/projects/laserblog/files/log/2026-11-18.md`:
1. `GENERATED_MARK` line.
2. YAML front matter: `date`, `device`, `sessions` (start, end, jobs), `projects` (paths relative to `~/projects/laserblog/files` when inside it, else absolute), `tests` (time, kind `grid`).
3. `# Wed Nov 18, 2026` + a summary line `**9 jobs · 19:16 to 21:18 · 1 project**`.
4. A day notes block.
5. One section per session: a jobs table (`#`, Time, Project, Settings, Result) and a notes block per job (`notes:job-HHMMSS`). Settings is a decoded summary (`5 to 50 mm/s × 10 to 100%`), otherwise `not captured`.
6. Per project file in the session: a layers table from `versions(project, first job time)`, with its `source` shown. `(unsaved project)` when `project is None`. `file no longer at this path` when `source == "missing"`.
7. Per job whose settings form a `grid`: a speed × power table with ✎ cells.

- [ ] **Step 1: Write failing tests:**
  - `test_mark_and_title`: output starts with `GENERATED_MARK` and contains `# Wed Nov 18, 2026`.
  - `test_unsaved_and_missing` (Review Focus 3): jobs with `project=None` and a nonexistent path render `(unsaved project)` and `file no longer at this path`.
  - `test_grid_table_rendered`: stored 6×6 settings for 20:45:45 → a table header `| Speed ↓ / Power → | 10% | 28% | 46% | 64% | 82% | 100% |`
  - `test_merge_keeps_notes`: existing page with `<!-- notes:job-204545:start -->\ncut through at 14\n<!-- notes:job-204545:end -->` → merged output contains `cut through at 14` inside the same block.
  - `test_merge_orphaned_notes` (Review Focus 5): existing notes block `job-999999` not present in generated → appears under `## Orphaned notes`.
  - `test_no_em_dashes`: `"—" not in output`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `merge_notes`: regex-collect `(id, body)` from existing, substitute into generated blocks with the same id, and append leftovers. Template via the existing `PackageLoader("maker_file_index", "templates")` pattern, with autoescape off for `.md`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: render laser log day pages and preserve notes`

### Task 7: `laser-log build` CLI, backfill, and auto-run

**Files:**
- Create: `src/maker_file_index/logbook/cli.py`, `~/Library/LaunchAgents/com.richgibson.laser-log.plist` (outside the repo; document it in README)
- Modify: `pyproject.toml` `[project.scripts]` add `laser-log = "maker_file_index.logbook.cli:main"`. `README.md`: a "Laser logbook" section.
- Test: `tests/logbook/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str] | None = None) -> int` with `build` subcommand:
  - `--log-dir PATH` (required)
  - `--jobs-csv PATH` (default `~/Documents/LightBurnJobs.csv`)
  - `--debug-log PATH` (default `~/Documents/LightBurnLog.txt`)
  - `--day YYYY-MM-DD` or `--all` (default: today)
  - Flow: read stream jobs → `save_stream_job` each → for each day: `render_day`, then write only if the file is absent **or** starts with `GENERATED_MARK` (merged via `merge_notes`). Otherwise print `skipped <path>: not generated by laser-log`. Prints `wrote N pages, skipped M` and returns 0.

- [ ] **Step 1: Write failing tests:**
  - `test_build_writes_day_page`: tmp CSV with 2 jobs on 2026-11-18, empty debug log → `log/2026-11-18.md` exists and starts with `GENERATED_MARK`.
  - `test_build_skips_hand_written_page`: a pre-existing `log/2026-11-18.md` without the mark is byte-identical after build, and stdout contains `skipped`.
  - `test_build_all_backfills`: CSV spanning 3 days with `--all` → 3 pages.
  - `test_rebuild_preserves_notes`: build, insert text into a notes block, build again → text still there.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**, then reinstall for the new entry point: `conda run -n drinkbotos pip install -e .`
- [ ] **Step 4: Run, expect PASS**, then the full suite: `conda run -n drinkbotos python -m pytest -q` (48 existing + new, all pass).
- [ ] **Step 5: Real backfill:** `conda run -n drinkbotos laser-log build --all --log-dir ~/projects/laserblog/files/log`
  - Expected: about 162 pages written, `skipped .../2026-11-18.md`.
  - Spot-check 2026-03-10 (should show `git <hash>` sources) and 2024-10 days (`current file`).
  - Check `log/jobs/2026-11-18/` has `204545.json` and `211853.json` with 37 settings (36 grid + labels) and 36+ settings respectively.
- [ ] **Step 6: Auto-run.** launchd plist with `StartInterval` 300 running `laser-log build --log-dir ~/projects/laserblog/files/log` (today only), PATH including the conda env bin, log to `~/Library/Logs/laser-log.log`. Load it with `launchctl bootstrap gui/$(id -u) ...` and confirm one run in the log.
- [ ] **Step 7: Commit** `feat: laser-log build command with backfill`
