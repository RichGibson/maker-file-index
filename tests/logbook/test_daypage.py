from datetime import date, datetime
from pathlib import Path

from maker_file_index.logbook.daypage import GENERATED_MARK, merge_notes, render_day
from maker_file_index.logbook.jobs import Job
from maker_file_index.logbook.projectfile import FileVersion, Layer
from maker_file_index.logbook.ruida import Setting

DAY = date(2026, 11, 18)
P = Path("/x/valet_small.lbrn2")


def job(hms, project=P):
    h, m, s = map(int, hms.split(":"))
    return Job(datetime(2026, 11, 18, h, m, s), "Ruida 6445S", project, "")


def versions(project, when):
    if "gone" in str(project):
        return FileVersion("missing", [])
    return FileVersion("git abc123", [Layer(0, "C00", "Cut", 20.0, 90.0, 90.0, 1, 158)])


def grid_settings():
    return [Setting(float(v), float(p), float(p)) for v in (5, 14, 23, 32, 41, 50) for p in (10, 28, 46, 64, 82, 100)]


def page(jobs, stored=None):
    return render_day(DAY, jobs, stored or {}, versions)


def test_mark_and_title():
    out = page([job("19:16:11")])
    assert out.startswith(GENERATED_MARK)
    assert "# Wed Nov 18, 2026" in out


def test_unsaved_and_missing():
    out = page([job("19:16:11", None), job("19:20:00", Path("/x/gone.lbrn2"))])
    assert "(unsaved project)" in out
    assert "file no longer at this path" in out


def test_grid_table_rendered():
    out = page([job("20:45:45")], {datetime(2026, 11, 18, 20, 45, 45, 124000): grid_settings()})
    assert "| Speed ↓ / Power → | 10% | 28% | 46% | 64% | 82% | 100% |" in out


def test_merge_keeps_notes():
    generated = page([job("20:45:45")])
    existing = generated.replace("<!-- notes:job-204545:start -->✎<!-- notes:job-204545:end -->",
                                 "<!-- notes:job-204545:start -->\ncut through at 14\n<!-- notes:job-204545:end -->")
    assert existing != generated
    merged = merge_notes(existing, generated)
    assert "<!-- notes:job-204545:start -->\ncut through at 14\n<!-- notes:job-204545:end -->" in merged


def test_merge_orphaned_notes():
    generated = page([job("20:45:45")])
    existing = generated + "\n<!-- notes:job-999999:start -->keep me<!-- notes:job-999999:end -->\n"
    merged = merge_notes(existing, generated)
    assert "## Orphaned notes" in merged
    assert "keep me" in merged


def test_no_em_dashes():
    out = page([job("19:16:11"), job("20:45:45", None)], {datetime(2026, 11, 18, 20, 45, 45): grid_settings()})
    assert "—" not in out


def test_grid_cell_edits_survive_merge():
    stored = {datetime(2026, 11, 18, 20, 45, 45, 124000): grid_settings()}
    generated = page([job("20:45:45")], stored)
    edited = generated.replace("| **14 mm/s** | ✎ | ✎ | ✎ |", "| **14 mm/s** | no | no | THROUGH |", 1)
    assert edited != generated
    assert "THROUGH" in merge_notes(edited, generated)


def test_unsafe_when_end_marker_damaged():
    from maker_file_index.logbook.daypage import unsafe_to_merge
    generated = page([job("20:45:45")])
    assert unsafe_to_merge(generated) is None
    assert unsafe_to_merge(generated.replace("<!-- notes:job-204545:end -->", "<!-- notes:job-204545:en", 1))


def test_unsafe_when_text_after_end_marker():
    from maker_file_index.logbook.daypage import unsafe_to_merge
    generated = page([job("20:45:45")])
    assert unsafe_to_merge(generated.replace("<!-- notes:job-204545:end -->", "<!-- notes:job-204545:end --> cut through", 1))


def test_unsafe_when_duplicate_ids():
    from maker_file_index.logbook.daypage import unsafe_to_merge
    block = "<!-- notes:job-1:start -->a<!-- notes:job-1:end -->\n"
    assert unsafe_to_merge(GENERATED_MARK + "\n" + block + block)


def test_same_second_jobs_get_unique_ids():
    from maker_file_index.logbook.daypage import unsafe_to_merge
    out = page([job("19:16:11"), job("19:16:11")])
    assert "notes:job-191611:start" in out and "notes:job-191611-2:start" in out
    assert unsafe_to_merge(out) is None


def test_thumbnail_shown_when_saved():
    def thumbs(project, when):
        return FileVersion("git abc123", [Layer(0, "C00", "Cut", 20.0, 90.0, 90.0, 1, 1)], b"\x89PNGx")
    out = render_day(DAY, [job("19:16:11")], {}, thumbs, save_thumb=lambda b: "images/thumbs/abc.png")
    assert "![valet_small.lbrn2 thumbnail](images/thumbs/abc.png)" in out


def test_no_thumbnail_line_without_image():
    assert "thumbnail](" not in page([job("19:16:11")])
