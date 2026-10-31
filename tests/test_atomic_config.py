"""t1043 — config.local.json is irreplaceable (git-ignored, personal): a torn write must
never reach it. The write has to go through a temp file + os.replace."""
import json
from pathlib import Path

import pytest

import noosconf
from tools import youtube_subs


@pytest.fixture
def local_cfg(tmp_path, monkeypatch):
    cfg = tmp_path / "config.local.json"
    cfg.write_text(json.dumps(
        {"astro": {"birth": "secret"},
         "probes": {"youtube": {"channels": [{"name": "a", "id": "UC1"}]}}}, indent=2))
    cfg.chmod(0o600)
    monkeypatch.setattr(youtube_subs, "path", lambda *a, **k: tmp_path)
    return cfg


def torn_write(monkeypatch):
    """Every Path.write_text writes half the payload and dies — a crash mid-write."""
    def torn(self, text, *args, **kwargs):
        with open(self, "w") as fh:
            fh.write(text[: len(text) // 2])
        raise OSError("disk full")
    monkeypatch.setattr(Path, "write_text", torn)


def test_failed_write_leaves_config_intact(monkeypatch, local_cfg):
    """TC1: the torn write must land on a temp file, never on config.local.json itself."""
    torn_write(monkeypatch)
    with pytest.raises(OSError):
        youtube_subs.append_channels([{"name": "b", "id": "UC2"}])
    data = json.loads(local_cfg.read_text())      # still parses
    assert data["astro"]["birth"] == "secret"


def test_append_preserves_mode_and_keys(local_cfg):
    """TC2: a successful append keeps mode 600 and the unrelated keys."""
    youtube_subs.append_channels([{"name": "b", "id": "UC2"}])
    assert local_cfg.stat().st_mode & 0o777 == 0o600
    data = json.loads(local_cfg.read_text())
    assert data["astro"]["birth"] == "secret"
    assert [c["id"] for c in data["probes"]["youtube"]["channels"]] == ["UC1", "UC2"]


def test_atomic_write_text(tmp_path, monkeypatch):
    """TC3: content replaced atomically, permissions preserved, no temp file left behind."""
    f = tmp_path / "x.json"
    f.write_text("old")
    f.chmod(0o600)
    noosconf.atomic_write_text(f, "new")
    assert f.read_text() == "new"
    assert f.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [f]
