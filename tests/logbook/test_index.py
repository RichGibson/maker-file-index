from datetime import date, datetime
from pathlib import Path

from maker_file_index.logbook.daypage import GENERATED_MARK
from maker_file_index.logbook.index import day_note_summary, render_index
from maker_file_index.logbook.jobs import Job
from maker_file_index.logbook.ruida import Setting

GRID = [Setting(float(v), float(p), float(p)) for v in (5, 14, 23) for p in (10, 28, 46)]


def j(ts, project="/x/valet_small.lbrn2"):
    return Job(datetime.fromisoformat(ts), "Ruida 6445S", Path(project) if project else None, "")


BY_DAY = {
    date(2026, 10, 2): [j("2026-10-02T10:00:00", None)],
    date(2026, 11, 18): [j("2026-11-18T19:16:11"), j("2026-11-18T20:45:45"),
                         j("2026-11-18T22:40:10", "/x/FloralPumpkinEarrings.lbrn2")],
}
STORED = {date(2026, 11, 18): {datetime(2026, 11, 18, 20, 45, 45, 124000): GRID}}


def test_newest_first_with_links():
    out = render_index(BY_DAY, STORED, {})
    assert out.startswith(GENERATED_MARK)
    assert out.index("(2026-11-18.md)") < out.index("(2026-10-02.md)")


def test_summary_counts_and_projects():
    line = next(l for l in render_index(BY_DAY, STORED, {}).splitlines() if "2026-11-18.md" in l)
    assert "3 jobs" in line and "19:16 to 22:40" in line
    assert "valet_small" in line and "FloralPumpkinEarrings" in line
    assert "1 material test" in line


def test_unsaved_project_named():
    line = next(l for l in render_index(BY_DAY, STORED, {}).splitlines() if "2026-10-02.md" in l)
    assert "(unsaved)" in line


def test_month_headings():
    out = render_index(BY_DAY, STORED, {})
    assert out.index("## November 2026") < out.index("## October 2026")


def test_day_note_shown():
    out = render_index(BY_DAY, STORED, {date(2026, 11, 18): "Material: 1/8 plywood"})
    assert "Material: 1/8 plywood" in out


def test_day_note_summary_picks_first_text_line():
    page = (GENERATED_MARK + "\n<!-- notes:start -->\n\n**Material:** 1/8\" plywood.\n\n"
            "![photo](images/a.jpg)\n<!-- notes:end -->\n")
    assert day_note_summary(page) == 'Material: 1/8" plywood.'
    assert day_note_summary(GENERATED_MARK + "\n<!-- notes:start -->✎<!-- notes:end -->") is None


def test_month_heading_separated_and_thousands():
    big = {date(2026, 11, 18): [j("2026-11-18T19:16:11")] * 1000, date(2026, 10, 2): [j("2026-10-02T10:00:00")]}
    out = render_index(big, {}, {})
    assert "\n\n## October 2026" in out
    assert "1,001 jobs" in out
