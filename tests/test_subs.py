"""t1040: subscription diff — pure, no OAuth, no network."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "youtube_subs", Path(__file__).resolve().parents[1] / "status" / "tools" / "youtube_subs.py")
subs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(subs)


def test_new_channel_detected():
    stored = {"UC_a", "UC_b"}
    fetched = [{"id": "UC_a", "name": "A"}, {"id": "UC_b", "name": "B"},
               {"id": "UC_c", "name": "C"}]
    new, removed = subs.diff_subs(stored, fetched)
    assert [n["id"] for n in new] == ["UC_c"]
    assert removed == []


def test_removed_channel_reported_not_deleted():
    stored = {"UC_a", "UC_b"}
    fetched = [{"id": "UC_a", "name": "A"}]
    new, removed = subs.diff_subs(stored, fetched)
    assert new == []
    assert removed == ["UC_b"]


def test_no_changes():
    stored = {"UC_a"}
    fetched = [{"id": "UC_a", "name": "A"}]
    new, removed = subs.diff_subs(stored, fetched)
    assert new == [] and removed == []
