"""t1046 — the watcher must survive a torn state file, and must not record a warn as sent
when notify.sh failed (a lost send would never retry: warn only fires on signature change)."""
import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status"))

watch = importlib.import_module("watch")

WARN = json.dumps([{"id": "loe", "severity": "warn", "text": "нова черга",
                    "value": {"schedule": "s1", "updated": "u1"}}])


def fake_run(probes_json, notify_rc, calls):
    """Dispatch subprocess.run: run.sh returns the probe list, notify.sh returns notify_rc."""
    def run(cmd, **kw):
        calls.append(cmd)
        if str(cmd[0]).endswith("run.sh"):
            return types.SimpleNamespace(stdout=probes_json, returncode=0)
        return types.SimpleNamespace(stdout="", returncode=notify_rc)
    return run


def test_corrupt_state_does_not_crash(monkeypatch, tmp_path):
    """TC1: truncated watch.json → the run still works and leaves valid state behind."""
    st = tmp_path / "watch.json"
    st.write_text('{"loe": {"sig": ')
    monkeypatch.setattr(watch, "STATE", st)
    calls = []
    monkeypatch.setattr(watch.subprocess, "run", fake_run(WARN, 0, calls))
    monkeypatch.setattr(watch.sys, "exit", lambda *a: None)
    watch.main()
    assert json.loads(st.read_text())["loe"]["sig"] == "s1|u1"


def test_failed_send_keeps_old_state(monkeypatch, tmp_path):
    """TC2: notify.sh fails → the new warn signature must not be persisted, so the next run
    retries the send instead of counting it as delivered."""
    st = tmp_path / "watch.json"
    monkeypatch.setattr(watch, "STATE", st)
    calls = []
    monkeypatch.setattr(watch.subprocess, "run", fake_run(WARN, 1, calls))
    monkeypatch.setattr(watch.sys, "exit", lambda *a: None)
    watch.main()
    saved = json.loads(st.read_text()) if st.exists() else {}
    assert saved.get("loe", {}).get("sig") != "s1|u1"


def test_successful_send_persists_and_silences(monkeypatch, tmp_path):
    """TC3: delivered warn is recorded; the same signature sends nothing next run."""
    st = tmp_path / "watch.json"
    monkeypatch.setattr(watch, "STATE", st)
    calls = []
    monkeypatch.setattr(watch.subprocess, "run", fake_run(WARN, 0, calls))
    monkeypatch.setattr(watch.sys, "exit", lambda *a: None)
    watch.main()
    assert json.loads(st.read_text())["loe"]["sig"] == "s1|u1"
    notifies = [c for c in calls if str(c[0]).endswith("notify.sh")]
    assert len(notifies) == 1
    watch.main()
    notifies = [c for c in calls if str(c[0]).endswith("notify.sh")]
    assert len(notifies) == 1, "unchanged warn was re-sent"
