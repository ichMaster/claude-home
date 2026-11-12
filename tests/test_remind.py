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


# --- t1167: a nudge is recorded as sent only when notify.sh actually delivered it -------

def _event_in_lead_window(now):
    start = (now + timedelta(minutes=remind.LEAD)).isoformat(timespec="seconds")
    return {"t1": {"status": "open", "title": "тест",
                   "events": [{"event": "ev1", "start": start, "end": ""}]}}


def _run_with_notify_rc(monkeypatch, tmp_path, rc):
    import types
    st = tmp_path / "reminders.json"
    monkeypatch.setattr(remind, "STATE", st)
    monkeypatch.setattr(remind, "asleep", lambda now: False)
    monkeypatch.setattr(remind, "task_state",
                        lambda: _event_in_lead_window(datetime.now()))
    monkeypatch.setattr(remind.subprocess, "run",
                        lambda *a, **kw: types.SimpleNamespace(returncode=rc,
                                                               stdout="", stderr=""))
    remind.main()
    return json.loads(st.read_text()) if st.exists() else {}


def test_failed_send_is_not_recorded(monkeypatch, tmp_path):
    """TC1 (t1167): notify.sh exits 1 → the key must not be recorded, so the next tick
    retries inside the window instead of losing the nudge forever."""
    saved = _run_with_notify_rc(monkeypatch, tmp_path, 1)
    assert "ev1:lead" not in saved


def test_delivered_send_is_recorded(monkeypatch, tmp_path):
    """TC2 (t1167): notify.sh exits 0 → recorded, so it is not sent twice."""
    saved = _run_with_notify_rc(monkeypatch, tmp_path, 0)
    assert "ev1:lead" in saved
