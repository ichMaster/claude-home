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


def fake_run(probes_json, notify_rc, calls, probe_timeout=False, notify_timeout=False):
    """Dispatch run_bounded: run.sh returns the probe list, notify.sh returns notify_rc.
    A timed-out call is None, the same contract as the real runner (t1201)."""
    def run(cmd, timeout=None):
        calls.append(cmd)
        if str(cmd[0]).endswith("run.sh"):
            return None if probe_timeout else (0, probes_json)
        return None if notify_timeout else (notify_rc, "")
    return run


def test_corrupt_state_does_not_crash(monkeypatch, tmp_path):
    """TC1: truncated watch.json → the run still works and leaves valid state behind."""
    st = tmp_path / "watch.json"
    st.write_text('{"loe": {"sig": ')
    monkeypatch.setattr(watch, "STATE", st)
    calls = []
    monkeypatch.setattr(watch, "run_bounded", fake_run(WARN, 0, calls))
    monkeypatch.setattr(watch.sys, "exit", lambda *a: None)
    watch.main()
    assert json.loads(st.read_text())["loe"]["sig"] == "s1|u1"


def test_failed_send_keeps_old_state(monkeypatch, tmp_path):
    """TC2: notify.sh fails → the new warn signature must not be persisted, so the next run
    retries the send instead of counting it as delivered."""
    st = tmp_path / "watch.json"
    monkeypatch.setattr(watch, "STATE", st)
    calls = []
    monkeypatch.setattr(watch, "run_bounded", fake_run(WARN, 1, calls))
    monkeypatch.setattr(watch.sys, "exit", lambda *a: None)
    watch.main()
    saved = json.loads(st.read_text()) if st.exists() else {}
    assert saved.get("loe", {}).get("sig") != "s1|u1"


def test_successful_send_persists_and_silences(monkeypatch, tmp_path):
    """TC3: delivered warn is recorded; the same signature sends nothing next run."""
    st = tmp_path / "watch.json"
    monkeypatch.setattr(watch, "STATE", st)
    calls = []
    monkeypatch.setattr(watch, "run_bounded", fake_run(WARN, 0, calls))
    monkeypatch.setattr(watch.sys, "exit", lambda *a: None)
    watch.main()
    assert json.loads(st.read_text())["loe"]["sig"] == "s1|u1"
    notifies = [c for c in calls if str(c[0]).endswith("notify.sh")]
    assert len(notifies) == 1
    watch.main()
    notifies = [c for c in calls if str(c[0]).endswith("notify.sh")]
    assert len(notifies) == 1, "unchanged warn was re-sent"


# --- t1168: an empty or malformed run.sh output must not wipe the dedup state ----------

def test_empty_run_output_keeps_state(monkeypatch, tmp_path):
    """TC1 (t1168): run.sh returned nothing (it crashed) → watch.json stays as it was,
    otherwise every active warn re-sends next tick and the alert clock resets."""
    st = tmp_path / "watch.json"
    old = {"loe": {"sig": "s1|u1", "sev": "warn", "sent": 123.0}}
    st.write_text(json.dumps(old))
    monkeypatch.setattr(watch, "STATE", st)
    monkeypatch.setattr(watch, "run_bounded", fake_run("", 0, []))
    watch.main()
    assert json.loads(st.read_text()) == old


def test_malformed_run_output_keeps_state(monkeypatch, tmp_path):
    """TC2 (t1168): torn cache line → run.sh prints garbage → no crash, state untouched."""
    st = tmp_path / "watch.json"
    old = {"loe": {"sig": "s1|u1", "sev": "warn", "sent": 123.0}}
    st.write_text(json.dumps(old))
    monkeypatch.setattr(watch, "STATE", st)
    monkeypatch.setattr(watch, "run_bounded", fake_run('{"half', 0, []))
    watch.main()
    assert json.loads(st.read_text()) == old


# --- t1201: a wedged probe must not hang the watcher (and so the timer) forever --------

def test_group_kill_returns_despite_surviving_child():
    """TC1 (t1201): a grandchild that outlives the shell holds the stdout pipe open; a
    naive kill-the-shell leaves communicate() blocked on it. run_bounded must kill the
    whole process group and come back None well before the grandchild's own exit."""
    import time as _t
    t0 = _t.monotonic()
    res = watch.run_bounded(["bash", "-c", "sleep 30 & exec sleep 30"], timeout=0.3)
    assert res is None
    assert _t.monotonic() - t0 < 5


def test_probe_timeout_keeps_state(monkeypatch, tmp_path):
    """TC2 (t1201): run.sh timed out → same contract as empty output (t1168): the run ends,
    state stays as it was."""
    st = tmp_path / "watch.json"
    old = {"loe": {"sig": "s1|u1", "sev": "warn", "sent": 123.0}}
    st.write_text(json.dumps(old))
    monkeypatch.setattr(watch, "STATE", st)
    monkeypatch.setattr(watch, "run_bounded", fake_run(WARN, 0, [], probe_timeout=True))
    watch.main()
    assert json.loads(st.read_text()) == old


def test_notify_timeout_keeps_state(monkeypatch, tmp_path):
    """TC3 (t1201): notify.sh timed out → an undelivered send, like a nonzero rc (t1046):
    the new signature is not persisted, so the warn retries next run."""
    st = tmp_path / "watch.json"
    monkeypatch.setattr(watch, "STATE", st)
    monkeypatch.setattr(watch, "run_bounded", fake_run(WARN, 0, [], notify_timeout=True))
    watch.main()
    saved = json.loads(st.read_text()) if st.exists() else {}
    assert saved.get("loe", {}).get("sig") != "s1|u1"


# --- t1222: a yellow→red escalation is a change, not silence until the 3h reminder -------

def _alarm(level):
    return {"id": "alarm", "severity": "alert",
            "value": {"district_alert": True, "region_alert": True, "level": level}}


def test_alarm_level_change_changes_the_signature():
    """TC1: the same alert escalating to red must read as changed."""
    assert watch.signature(_alarm("yellow")) != watch.signature(_alarm("red"))


def test_alarm_same_level_keeps_the_signature():
    """TC2: no level change, no duplicate alert."""
    assert watch.signature(_alarm("red")) == watch.signature(_alarm("red"))
