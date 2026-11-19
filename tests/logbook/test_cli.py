from maker_file_index.logbook.cli import main
from maker_file_index.logbook.daypage import GENERATED_MARK

HEAD = "Timestamp,Device,Project,Sent File\n"


def setup(tmp_path, days=("2026-11-18",)):
    csv = tmp_path / "jobs.csv"
    csv.write_text(HEAD + "".join(f"{d}T19:16:11,Ruida 6445S,,\n{d}T20:45:45,Ruida 6445S,,\n" for d in days))
    log_dir = tmp_path / "log"
    args = ["build", "--log-dir", str(log_dir), "--jobs-csv", str(csv), "--debug-log", str(tmp_path / "none.txt")]
    return log_dir, args


def test_build_writes_day_page(tmp_path):
    log_dir, args = setup(tmp_path)
    assert main(args + ["--day", "2026-11-18"]) == 0
    assert (log_dir / "2026-11-18.md").read_text().startswith(GENERATED_MARK)


def test_build_skips_hand_written_page(tmp_path, capsys):
    log_dir, args = setup(tmp_path)
    log_dir.mkdir()
    page = log_dir / "2026-11-18.md"
    page.write_text("# my own page\n")
    main(args + ["--day", "2026-11-18"])
    assert page.read_text() == "# my own page\n"
    assert "skipped" in capsys.readouterr().out


def test_build_all_backfills(tmp_path):
    log_dir, args = setup(tmp_path, days=("2026-11-16", "2026-11-17", "2026-11-18"))
    main(args + ["--all"])
    assert sorted(p.name for p in log_dir.glob("2*.md")) == ["2026-11-16.md", "2026-11-17.md", "2026-11-18.md"]


def test_rebuild_preserves_notes(tmp_path):
    log_dir, args = setup(tmp_path)
    main(args + ["--day", "2026-11-18"])
    page = log_dir / "2026-11-18.md"
    page.write_text(page.read_text().replace("<!-- notes:start -->✎", "<!-- notes:start -->walnut too dark"))
    main(args + ["--day", "2026-11-18"])
    assert "walnut too dark" in page.read_text()


def test_default_builds_yesterday_too(tmp_path):
    from datetime import date, timedelta
    y = (date.today() - timedelta(days=1)).isoformat()
    log_dir, args = setup(tmp_path, days=(y,))
    main(args)
    assert (log_dir / f"{y}.md").exists()


def test_damaged_page_is_skipped(tmp_path, capsys):
    log_dir, args = setup(tmp_path)
    main(args + ["--day", "2026-11-18"])
    page = log_dir / "2026-11-18.md"
    damaged = page.read_text().replace("<!-- notes:end -->", "", 1).replace("<!-- notes:start -->✎", "<!-- notes:start -->precious", 1)
    page.write_text(damaged)
    main(args + ["--day", "2026-11-18"])
    assert page.read_text() == damaged
    assert "skipped" in capsys.readouterr().out


def test_build_writes_index(tmp_path):
    log_dir, args = setup(tmp_path, days=("2026-11-16", "2026-11-18"))
    main(args + ["--all"])
    index = (log_dir / "index.md").read_text()
    assert index.startswith(GENERATED_MARK)
    assert index.index("2026-11-18.md") < index.index("2026-11-16.md")
