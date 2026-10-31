"""t1048 — parse_due must treat an impossible dotted date as not-a-date instead of crashing
add (/task from Telegram dies), and defer must refuse an unparseable date instead of
silently wiping the existing deadline."""
import json

import pytest

import store


def test_parse_due_version_number_does_not_crash():
    """TC1: 'python 3.14' is a version, not the 3rd of month 14."""
    due, title = store.parse_due("оновити python 3.14")
    assert due is None
    assert "3.14" in title


def test_parse_due_impossible_day_does_not_crash():
    due, title = store.parse_due("звіт до 31.11")
    assert due is None
    assert "31.11" in title


def test_parse_due_valid_date_still_works():
    due, _ = store.parse_due("звіт до 30.11")
    assert due is not None and (due.day, due.month) == (30, 11)


@pytest.fixture
def task_log(tmp_path, monkeypatch):
    log = tmp_path / "tasks.jsonl"
    log.write_text(json.dumps({"op": "add", "id": "t001", "title": "тест",
                               "due": "2026-11-05", "ts": "2026-10-31T05:00:00+02:00"},
                              ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(store, "LOG", log)
    monkeypatch.setattr(store, "VIEW", tmp_path / "open.md")
    return log


def test_defer_unparseable_date_keeps_due(monkeypatch, task_log):
    """TC2: a phrase parse_due cannot read must not append due: null."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "колись-потім"])
    with pytest.raises(SystemExit):
        store.main()
    assert store.state()["t001"]["due"] == "2026-11-05"


def test_defer_valid_date_still_works(monkeypatch, task_log):
    """TC3: a parseable defer still moves the date."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "завтра"])
    store.main()
    assert store.state()["t001"]["due"] is not None
    assert store.state()["t001"]["due"] != "2026-11-05"


# t1075 — defer must understand the same period phrases add does: the panel's weekend
# button sends «на вихідних», which parse_due alone cannot read.

def test_defer_to_the_weekend_sets_a_period_and_clears_due(monkeypatch, task_log):
    """TC1: the board's «вихідні» button must move the task, not fail every press."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "на вихідних"])
    store.main()
    t = store.state()["t001"]
    assert t["period"] and t["period"][0] == "вихідні"
    assert t["due"] is None, "a period defer clears the hard date — the date is the stronger claim"


def test_defer_to_a_date_keeps_an_existing_period(monkeypatch, task_log):
    """TC2: a date defer behaves as before and does not touch the period."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "на вихідних"])
    store.main()
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "завтра"])
    store.main()
    t = store.state()["t001"]
    assert t["due"] is not None
    assert t["period"] and t["period"][0] == "вихідні"


def test_old_defer_events_replay_unchanged(task_log):
    """TC4: a defer line without a period key must not invent or wipe one."""
    with task_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"op": "defer", "id": "t001", "due": "2026-11-07",
                            "ts": "2026-10-31T06:00:00+02:00"}) + "\n")
    t = store.state()["t001"]
    assert t["due"] == "2026-11-07"
    assert t.get("period") is None
