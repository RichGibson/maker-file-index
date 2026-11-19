from datetime import date, datetime
from pathlib import Path

from maker_file_index.logbook.jobs import jobs_by_day, read_jobs, sessions

HEAD = "Timestamp,Device,Project,Sent File\n"


def csv_file(tmp_path, rows):
    p = tmp_path / "LightBurnJobs.csv"
    p.write_text(HEAD + "".join(rows))
    return p


def test_blank_project_is_none(tmp_path):
    (job,) = read_jobs(csv_file(tmp_path, ["2026-11-18T19:16:11,Ruida 6445S,,\n"]))
    assert job.project is None
    assert job.when == datetime(2026, 11, 18, 19, 16, 11)


def test_sent_file_kept(tmp_path):
    (job,) = read_jobs(csv_file(tmp_path, ["2024-08-18T21:05:28,Ruida 644XS,/x/coasters.lbrn2,COASTERS\n"]))
    assert job.sent_file == "COASTERS"
    assert job.project == Path("/x/coasters.lbrn2")


def test_sessions_split_on_45_min(tmp_path):
    rows = [f"2026-11-18T{t},Ruida 6445S,/x/a.lbrn2,\n" for t in ("19:16:00", "19:31:00", "20:18:00", "21:18:00")]
    groups = sessions(read_jobs(csv_file(tmp_path, rows)))
    assert [[j.when.strftime("%H:%M") for j in g] for g in groups] == [["19:16", "19:31"], ["20:18"], ["21:18"]]


def test_jobs_by_day(tmp_path):
    rows = ["2026-11-16T22:00:00,R,/x/a.lbrn2,\n", "2026-11-18T19:16:11,R,/x/a.lbrn2,\n", "2026-11-18T20:00:00,R,,\n"]
    days = jobs_by_day(read_jobs(csv_file(tmp_path, rows)))
    assert sorted(days) == [date(2026, 11, 16), date(2026, 11, 18)]
    assert len(days[date(2026, 11, 18)]) == 2
