import os
import subprocess
from datetime import datetime

from maker_file_index.logbook.projectfile import FileVersion, Layer, layers_from_bytes, version_at


PNG = b"\x89PNG\r\n\x1a\nfake"


def lbrn(speed, power, shapes=1, thumb=None):
    import base64
    shape = '<Shape Type="Path" CutIndex="0"/>' * shapes
    t = f'<Thumbnail Source="{base64.b64encode(thumb).decode()}"/>' if thumb else ""
    return (f'<LightBurnProject>{t}<CutSetting type="Cut"><index Value="0"/><name Value="C00"/>'
            f'<speed Value="{speed}"/><maxPower Value="{power}"/><minPower Value="{power}"/></CutSetting>'
            f'{shape}</LightBurnProject>').encode()


def commit(repo, name, data, when):
    (repo / name).write_bytes(data)
    env = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", name], check=True, env=env)
    subprocess.run(git + ["commit", "-q", "-m", name], check=True, env=env)


def test_power_parsed():
    (layer,) = layers_from_bytes(lbrn(14, 60))
    assert layer == Layer(index=0, name="C00", mode="Cut", speed=14.0, min_power=60.0, max_power=60.0, passes=1, shapes=1)


def test_shapes_counted():
    assert layers_from_bytes(lbrn(14, 60, shapes=2))[0].shapes == 2


def test_version_at_uses_git(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    commit(tmp_path, "a.lbrn2", lbrn(10, 50), "2026-03-01T10:00:00")
    commit(tmp_path, "a.lbrn2", lbrn(20, 50), "2026-03-03T10:00:00")
    v = version_at(tmp_path / "a.lbrn2", datetime(2026, 3, 2, 12, 0))
    assert v.source.startswith("git ")
    assert v.layers[0].speed == 10.0


def test_version_at_prefers_newer_backup(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    commit(tmp_path, "a.lbrn2", lbrn(10, 50), "2026-03-01T10:00:00")
    commit(tmp_path, "a_backup.lbrn2", lbrn(30, 50), "2026-03-01T11:00:00")
    v = version_at(tmp_path / "a.lbrn2", datetime(2026, 3, 1, 12, 0))
    assert v.layers[0].speed == 30.0


def test_missing_file(tmp_path):
    assert version_at(tmp_path / "gone.lbrn2", datetime(2026, 1, 1)) == FileVersion("missing", [])


def test_thumbnail_from_git_version(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    commit(tmp_path, "a.lbrn2", lbrn(10, 50, thumb=PNG), "2026-03-01T10:00:00")
    commit(tmp_path, "a.lbrn2", lbrn(20, 50, thumb=PNG + b"v2"), "2026-03-03T10:00:00")
    assert version_at(tmp_path / "a.lbrn2", datetime(2026, 3, 2)).thumbnail == PNG


def test_no_thumbnail_is_none(tmp_path):
    (tmp_path / "a.lbrn2").write_bytes(lbrn(10, 50))
    assert version_at(tmp_path / "a.lbrn2", datetime(2026, 3, 2)).thumbnail is None
