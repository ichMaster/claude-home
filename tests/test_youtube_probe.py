"""t1044 — the youtube probe must trim its seen-set by recency (not lexicographically,
which evicts recently-seen ids and re-reports their videos) and survive a torn state file."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status" / "probes"))

yt = importlib.import_module("youtube")


def test_trim_keeps_newest_not_lexicographic():
    """TC1: ids seen last must survive the cap even when they sort lowest."""
    order = ["zz1", "yy2", "-a3", "0b4", "_c5"]      # newest three sort below the oldest two
    assert yt.trim_seen(order, cap=3) == ["-a3", "0b4", "_c5"]


def test_load_state_survives_corrupt_file(tmp_path):
    """TC2: a kill mid-write leaves truncated JSON — the probe must start fresh, not die."""
    f = tmp_path / "youtube.json"
    f.write_text('{"seen": ["a", "b"', encoding="utf-8")
    assert yt.load_state(f) == {}
    assert yt.load_state(tmp_path / "missing.json") == {}


def test_trim_dedup_keeps_latest_occurrence():
    """TC3: a re-seen id counts as fresh — its newest position decides survival."""
    order = ["a", "b", "c", "a"]
    assert yt.trim_seen(order, cap=2) == ["c", "a"]
