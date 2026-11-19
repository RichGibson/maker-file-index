from datetime import datetime

from maker_file_index.logbook.debuglog import read_stream_jobs

HEADER = '20:45:12.576  D: "LightBurn Pro 2.1.03"   "Wed Nov 18 2026"\n'


def write(tmp_path, body):
    p = tmp_path / "LightBurnLog.txt"
    p.write_text(HEADER + body)
    return p


def test_two_jobs_split(tmp_path):
    p = write(tmp_path,
              '20:45:45.124  D: Protocol::GenerateCuts time: 0\n'
              '20:45:45.604  D: O: "a1b2"\n'
              '20:45:45.605  D: O: "c3"\n'
              '21:18:53.711  D: Protocol::GenerateCuts time: 1\n'
              '21:18:53.800  D: O: "ff00"\n')
    jobs = read_stream_jobs(p)
    assert len(jobs) == 2
    assert jobs[0].started == datetime(2026, 11, 18, 20, 45, 45, 124000)
    assert jobs[0].raw == bytes.fromhex("a1b2c3")
    assert jobs[1].raw == bytes.fromhex("ff00")
    assert not jobs[0].truncated


def test_truncated_last_line(tmp_path):
    p = write(tmp_path,
              '21:18:53.711  D: Protocol::GenerateCuts time: 1\n'
              '21:18:53.800  D: O: "c40b0982077')
    (job,) = read_stream_jobs(p)
    assert job.truncated is True
    assert job.raw == bytes.fromhex("c40b098207")


def test_midnight_rollover(tmp_path):
    p = write(tmp_path,
              '23:59:50.000  D: Protocol::GenerateCuts time: 0\n'
              '00:00:10.000  D: Protocol::GenerateCuts time: 0\n')
    jobs = read_stream_jobs(p)
    assert jobs[1].started.date() == datetime(2026, 11, 19).date()


def test_missing_file_returns_empty(tmp_path):
    assert read_stream_jobs(tmp_path / "nope.txt") == []


def test_noise_lines_ignored(tmp_path):
    p = write(tmp_path,
              '20:45:45.124  D: Protocol::GenerateCuts time: 0\n'
              '20:45:45.200  D: EV: 1010 took 2272 uS\n'
              '20:45:45.325  D:   I: "d4090df70fc149fb99"\n'
              '20:45:45.604  D: O: "a1"\n')
    assert read_stream_jobs(p)[0].raw == b"\xa1"


def test_last_job_is_provisional(tmp_path):
    p = write(tmp_path, '20:45:45.124  D: Protocol::GenerateCuts time: 0\n')
    assert read_stream_jobs(p)[-1].truncated is True


def test_out_of_order_ms_does_not_roll_day(tmp_path):
    p = write(tmp_path,
              '20:45:45.200  D: Protocol::GenerateCuts time: 0\n'
              '20:45:45.199  D: EV: 1 took 1 uS\n'
              '21:00:00.000  D: Protocol::GenerateCuts time: 0\n')
    assert read_stream_jobs(p)[1].started.date() == datetime(2026, 11, 18).date()


def test_restart_header_resyncs_date(tmp_path):
    p = write(tmp_path,
              '20:45:45.124  D: Protocol::GenerateCuts time: 0\n'
              '22:00:00.000  D: "LightBurn Pro 2.1.03"   "Fri Nov 20 2026"\n'
              '22:05:00.000  D: Protocol::GenerateCuts time: 0\n')
    assert read_stream_jobs(p)[1].started == datetime(2026, 11, 20, 22, 5)
