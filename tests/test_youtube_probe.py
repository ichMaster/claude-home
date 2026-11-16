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


# t1191 — the archive is the one file in the probe still rewritten with a bare write_text;
# a power cut mid-write loses the 45-day history the feeds cannot give back.
import json
from datetime import datetime, timedelta, timezone


def _entry(link, when=None):
    when = when or (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    return {"channel": "к", "title": "т", "link": link, "published": when}


def test_archive_write_is_atomic(tmp_path, monkeypatch):
    """t1191 TC1: the archive is written through atomic_write_text, never a bare
    write_text — a kill mid-write must leave the old file, not a torn one."""
    calls = []

    def record(target, text, encoding="utf-8"):
        calls.append(Path(target))
        Path(target).write_text(text, encoding=encoding)

    monkeypatch.setattr(yt, "atomic_write_text", record)
    archive = tmp_path / "youtube-archive.jsonl"
    yt.update_archive(archive, [_entry("L1")])
    assert calls == [archive]
    assert json.loads(archive.read_text(encoding="utf-8").splitlines()[0])["link"] == "L1"


def test_archive_merges_dedupes_and_trims_by_age(tmp_path):
    """t1191 TC2: old records fall off, a fresh link already present is not duplicated,
    the rest survive the rewrite."""
    archive = tmp_path / "youtube-archive.jsonl"
    old = _entry("Lold", "2020-01-01T00:00:00+00:00")
    kept = _entry("Lkept")
    archive.write_text(json.dumps(old) + "\n" + json.dumps(kept) + "\n", encoding="utf-8")
    yt.update_archive(archive, [_entry("Lkept"), _entry("Lnew")])
    links = [json.loads(l)["link"] for l in archive.read_text(encoding="utf-8").splitlines()]
    assert links == ["Lkept", "Lnew"]


def test_archive_update_is_locked(tmp_path, monkeypatch):
    """t1191 TC3: the read-modify-write holds locked(archive), so two overlapping writers
    serialize instead of silently dropping each other's records."""
    used = []

    class FakeLock:
        def __init__(self, target):
            used.append(Path(target))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(yt, "locked", FakeLock)
    archive = tmp_path / "youtube-archive.jsonl"
    yt.update_archive(archive, [_entry("L1")])
    assert used == [archive]
