"""t1172 — a failed Telegram delivery of the morning reading must be detected.

notify.sh's exit code is the delivery verdict (t1121); mood.send() used to drop it, so the
08:15 reading could silently never arrive while the timer showed success and report_failure
(t1160) was never invoked.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "status"))
import mood
import mood2


def fake_run(returncode):
    def run(cmd, **kw):
        return types.SimpleNamespace(returncode=returncode, args=cmd)
    return run


def test_send_returns_false_when_notify_fails(monkeypatch):
    """TC1: a non-zero notify.sh exit is a failed delivery."""
    monkeypatch.setattr(mood.subprocess, "run", fake_run(1))
    assert mood.send("текст", voice="голос") is False


def test_send_returns_true_when_both_calls_land(monkeypatch):
    """TC1: both calls at 0 — delivered."""
    monkeypatch.setattr(mood.subprocess, "run", fake_run(0))
    assert mood.send("текст", voice="голос") is True


def test_mood2_send_raises_undelivered(monkeypatch):
    """TC2: v2's sender must not swallow a failed delivery."""
    monkeypatch.setattr(mood2, "placeholders", lambda: [])
    monkeypatch.setattr(mood2.mood, "send", lambda *a, **k: False)
    with pytest.raises(mood2.Undelivered):
        mood2.send("ДЕНЬ\nтекст читання")


def test_mood2_main_reports_a_failed_delivery(monkeypatch):
    """TC3: --send with a dead Telegram returns non-zero and says so in the chat."""
    reported = []
    monkeypatch.setattr(mood2, "require_config", lambda: None)
    monkeypatch.setattr(mood2, "stages", lambda: ["письмо"])
    monkeypatch.setattr(mood2, "run", lambda day, dry_run, note: {"письмо": "читання"})
    monkeypatch.setattr(mood2, "send",
                        lambda text: (_ for _ in ()).throw(mood2.Undelivered("нотіфай впав")))
    monkeypatch.setattr(mood2, "report_failure", lambda text: reported.append(text))
    monkeypatch.setattr(sys, "argv", ["mood2.py", "--send", "--day", "2026-11-13"])
    rc = mood2.main()
    assert rc != 0
    assert reported and "не надіслал" in reported[0]


# --- t1204: mood.json is written atomically, like every other state file ---------------

def test_state_writes_are_atomic(monkeypatch, tmp_path):
    """t1204: save_state and save_bio_state used a bare write_text (truncate, then write);
    a kill mid-write left torn JSON that zirka_context choked on. Both must go through
    atomic_write_text, and still produce the same valid state."""
    import json as _json
    from datetime import date as _date
    calls = []
    monkeypatch.setattr(mood, "state_path", lambda key: tmp_path / "mood.json")
    monkeypatch.setattr(mood, "atomic_write_text",
                        lambda p, s, **kw: calls.append((p, s)))
    mood.save_state(_date(2026, 11, 18), {"conclusion": "ок"},
                    {"day": "день", "claim_list": []}, "Ф+1")
    mood.save_bio_state(_date(2026, 11, 18), {"conclusion": "ок"}, "Ф+1")
    assert len(calls) == 2
    for p, s in calls:
        assert _json.loads(s)["day"] == "2026-11-18"
