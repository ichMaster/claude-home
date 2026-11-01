"""t1109 — configuration must not freeze at import in a 24/7 process.

Found by the full review (truth H4): `DATA = _load()` ran once, so in the panel — a process
that lives for weeks and now writes configuration itself — the Sources toggle, the Rules
permission table and the Prompt screen's permission block all kept stating the value the file
had when the process started.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import noosconf                                                         # noqa: E402


def two_configs(tmp_path, monkeypatch, default, local):
    (tmp_path / "config.json").write_text(json.dumps(default), encoding="utf-8")
    (tmp_path / "config.local.json").write_text(json.dumps(local), encoding="utf-8")
    monkeypatch.setattr(noosconf, "ROOT", tmp_path)
    monkeypatch.setattr(noosconf, "_CHECKED", 0.0)
    noosconf.DATA = noosconf._load()
    return tmp_path


def test_a_changed_file_is_picked_up_without_a_restart(tmp_path, monkeypatch):
    folder = two_configs(tmp_path, monkeypatch, {"a": {"b": 1}}, {})
    assert noosconf.conf("a.b") == 1
    (folder / "config.local.json").write_text(json.dumps({"a": {"b": 2}}),
                                              encoding="utf-8")
    monkeypatch.setattr(noosconf, "_CHECKED", 0.0)        # the freshness window has passed
    assert noosconf.conf("a.b") == 2


def test_a_file_that_stops_parsing_keeps_the_last_good_values(tmp_path, monkeypatch):
    """A half-written config must not blank the whole configuration of a running process."""
    folder = two_configs(tmp_path, monkeypatch, {"a": {"b": 1}}, {"a": {"b": 2}})
    assert noosconf.conf("a.b") == 2
    (folder / "config.local.json").write_text('{"a": {"b": ', encoding="utf-8")
    monkeypatch.setattr(noosconf, "_CHECKED", 0.0)
    assert noosconf.conf("a.b") == 2


def test_an_unchanged_file_is_not_read_again(tmp_path, monkeypatch):
    """The check is a stat, not a read, and it is throttled: this runs per `conf()` call in
    a request-serving loop."""
    two_configs(tmp_path, monkeypatch, {"a": 1}, {})
    reads = []
    real = noosconf._load
    monkeypatch.setattr(noosconf, "_load", lambda: (reads.append(1), real())[1])
    monkeypatch.setattr(noosconf, "_CHECKED", 0.0)
    for _ in range(50):
        noosconf.conf("a")
    assert len(reads) <= 1, f"{len(reads)} re-reads for an unchanged file"
