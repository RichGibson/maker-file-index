import json
from datetime import date, datetime

from maker_file_index.logbook.debuglog import StreamJob
from maker_file_index.logbook.ruida import Setting, swizzle
from maker_file_index.logbook.store import load_stored, match_stream, save_stream_job

T = datetime(2026, 11, 18, 20, 45, 45, 124000)


def n5(v):
    return [(v >> s) & 0x7F for s in (28, 21, 14, 7, 0)]


def p2(pct):
    r = round(pct * 0x3FFF / 100)
    return [(r >> 7) & 0x7F, r & 0x7F]


def stream(*settings):
    cmds = []
    for i, (v, p) in enumerate(settings):
        cmds += [0xCA, 0x02, i, 0xC9, 0x02, *n5(v * 1000), 0xC6, 0x01, *p2(p), 0xC6, 0x02, *p2(p)]
    return bytes(swizzle(b) for b in cmds)


def test_save_and_load_roundtrip(tmp_path):
    path = save_stream_job(tmp_path, StreamJob(started=T, raw=stream((14, 28))))
    assert path == tmp_path / "jobs" / "2026-11-18" / "204545.json"
    assert json.loads(path.read_text())["truncated"] is False
    assert load_stored(tmp_path, date(2026, 11, 18)) == {T: [Setting(14.0, 28.0, 28.0)]}


def test_log_reset_keeps_stored(tmp_path):
    save_stream_job(tmp_path, StreamJob(started=T, raw=stream((14, 28))))
    # LightBurn reset its log: no stream jobs this run, nothing saved
    assert load_stored(tmp_path, date(2026, 11, 18)) == {T: [Setting(14.0, 28.0, 28.0)]}


def test_longer_truncated_replaces_shorter(tmp_path):
    save_stream_job(tmp_path, StreamJob(started=T, raw=stream((14, 28)), truncated=True))
    save_stream_job(tmp_path, StreamJob(started=T, raw=stream((14, 28), (5, 46)), truncated=True))
    assert len(load_stored(tmp_path, date(2026, 11, 18))[T]) == 2


def test_truncated_never_overwrites_complete(tmp_path):
    save_stream_job(tmp_path, StreamJob(started=T, raw=stream((14, 28), (5, 46))))
    save_stream_job(tmp_path, StreamJob(started=T, raw=stream((14, 28), (5, 46), (9, 9)), truncated=True))
    assert len(load_stored(tmp_path, date(2026, 11, 18))[T]) == 2


def test_match_within_tolerance():
    stored = {T: [Setting(14.0, 28.0, 28.0)]}
    assert match_stream(datetime(2026, 11, 18, 20, 45, 45), stored) == [Setting(14.0, 28.0, 28.0)]
    assert match_stream(datetime(2026, 11, 18, 20, 46, 0), stored) is None


def test_empty_flush_then_full_flush_updates(tmp_path):
    from maker_file_index.logbook.debuglog import read_stream_jobs
    log = tmp_path / "LightBurnLog.txt"
    head = '20:45:12.576  D: "LightBurn Pro 2.1.03"   "Wed Nov 18 2026"\n20:45:45.124  D: Protocol::GenerateCuts time: 0\n'
    log.write_text(head)
    for j in read_stream_jobs(log):
        save_stream_job(tmp_path, j)
    log.write_text(head + f'20:45:45.604  D: O: "{stream((14, 28)).hex()}"\n')
    for j in read_stream_jobs(log):
        save_stream_job(tmp_path, j)
    assert load_stored(tmp_path, date(2026, 11, 18))[T] == [Setting(14.0, 28.0, 28.0)]
