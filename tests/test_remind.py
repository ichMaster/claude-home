"""t1050 — a reminders.json torn by a crash mid-write must not stop the nudge timer
forever: the state read falls back to {} and the run leaves valid state behind."""
import importlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status"))

remind = importlib.import_module("remind")


def test_corrupt_state_does_not_stop_reminders(monkeypatch, tmp_path):
    """TC1: truncated state → the run completes and rewrites valid JSON."""
    st = tmp_path / "reminders.json"
    st.write_text('{"ev1:lead": "2026-10-')
    monkeypatch.setattr(remind, "STATE", st)
    monkeypatch.setattr(remind, "asleep", lambda now: False)
    monkeypatch.setattr(remind, "task_state", lambda: {})
    remind.main()
    assert json.loads(st.read_text()) == {}


def test_recorded_nudge_not_resent(monkeypatch, tmp_path):
    """TC2: a lead nudge already in state is not sent again."""
    now = datetime.now()
    start = (now + timedelta(minutes=remind.LEAD)).isoformat(timespec="seconds")
    st = tmp_path / "reminders.json"
    st.write_text(json.dumps({"ev1:lead": now.isoformat(timespec="seconds")}))
    monkeypatch.setattr(remind, "STATE", st)
    monkeypatch.setattr(remind, "asleep", lambda now: False)
    monkeypatch.setattr(remind, "task_state", lambda: {
        "t1": {"status": "open", "title": "тест",
               "events": [{"event": "ev1", "start": start, "end": ""}]}})
    sent = []
    monkeypatch.setattr(remind, "notify", sent.append)
    remind.main()
    assert sent == []
