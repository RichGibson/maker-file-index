# Laser Logbook: Spec

Date: 2026-11-18. Source: design conversation with Rich (decisions quoted or summarized from that session).

## Problem

"I change power, try a test, then I lose track of what settings I used." Rich often has several LightBurn files open in one evening and cuts one selected item at a time. Of 246 sessions in his job history, 34% use 2+ files and 55 return to an earlier file.

## Data sources (all verified on 2026-11-18)

| Source | Path | Gives |
|---|---|---|
| LightBurn job history | `~/Documents/LightBurnJobs.csv` (header `Timestamp,Device,Project,Sent File`) | One row per job since 2024-08-12. Blank `Project` means an unsaved project. |
| LightBurn debug log | `~/Documents/LightBurnLog.txt` | `HH:MM:SS.mmm  D: ...` lines. The first line holds the date (`"LightBurn Pro 2.1.03"   "Wed Nov 18 2026"`). Each job starts with a `Protocol::GenerateCuts` line, followed by ` O: "<hex>"` lines: the bytes sent to the Ruida. Written in delayed batches. Whether it resets on restart is unknown. |
| Project files | `.lbrn2` and LightBurn autosave `<name>_backup.lbrn2` (every 120 s) | Layers (`CutSetting`: index, name, type, speed, maxPower, minPower, numPasses, interval). |
| File history | gitwatch auto-commits in `~/projects/laserblog/files` (launchd agent `com.richgibson.gitwatch-laserblog`, since 2026-11-18 21:21) plus 590 gitwatch commits from 2026-03-01 to 03-18 | File version at a job's time. |
| Photos | `~/Downloads/PXL_*.jpg` (Pixel, EXIF `DateTimeOriginal` in local time) | Result photos, matched by time **with confirmation** (a time-only match picked a non-laser photo). |

## Ruida stream (verified against both 2026-11-18 material tests)

- Unscramble each byte with magic `0x88`: `b=(b-1)&0xFF; b^=0x88; swap bit 7 and bit 0`.
- Numbers: 5 bytes of 7 bits, big-endian. Speed is in µm/s, so divide by 1000 for mm/s.
- Power: 2 bytes of 7 bits, `raw*100/0x3FFF` percent.
- Header per layer: `C9 04 <L> <n5>` speed, `C6 31 <L> <p2>` min power, `C6 32 <L> <p2>` max power. The header only covers layers 0 to 31.
- Body: `CA 02 <L>` selects a layer, `C9 02 <n5>` speed, `C6 01 <p2>` min power, `C6 02 <p2>` max power. The body covers every setting actually used.

## Decisions

- The log is **permanent Markdown in `~/projects/laserblog/files/log/`**, not in `maker_file_data/`, which is regenerable. Images go in `log/images/`, resized to 1600 px.
- **One page per day**: `log/YYYY-MM-DD.md`. Later indexes per project and per file point into the day pages.
- Read it as a web page. maker-file-index builds it. Notes are written in a web UI back into the Markdown, with **no database**. Rich may also hand-edit the Markdown.
- Notes live in `<!-- notes:<id>:start -->` / `<!-- notes:<id>:end -->` blocks (plain `notes:start`/`notes:end` for the day). Regeneration must never lose text inside them.
- Decoded job settings must be **stored durably** under `log/`, because the debug log may reset and will grow large.
- Backfill all 162 past days. Past days get job times, sessions, and layers from the nearest git version of the file, otherwise the current file (flagged as such).
- A material test shows up as a speed × power grid when the distinct settings form a full grid.

## Out of scope for the first plan

Photo matching (plan 2) and the `serve` notes UI (plan 3). Matching cut positions to items in the file (later).
