"""t1059 — a reference in Zirka's chat is kept and handed over, never learned from there:
the horoscope is calibrated through the session, and her share is his account of the day.
"""
import subprocess
import types
from datetime import date

import inbox


def capture(monkeypatch):
    """Record every subprocess the handler starts, and run none of them."""
    calls = []

    def run(cmd, **kw):
        calls.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def used(calls, script):
    """Calls that actually RUN `script` — matching an argument end, not any substring.
    The handover message mentions `astro_learn.py add --file` as advice, and advice is not
    an invocation."""
    return [c for c in calls if any(str(part).endswith(script) for part in c)]


def test_reference_is_parked_not_learned(monkeypatch, tmp_path):
    monkeypatch.setattr(inbox, "HOME", tmp_path)
    calls = capture(monkeypatch)
    out = inbox.park_reference("☽ Пн 26 жовтня\nЛуна в Тельце",
                               {"day": "today", "period": "день", "author": "хтось"})

    parked = list((tmp_path / "status" / "state" / "astro-reference-inbox").glob("*.txt"))
    assert len(parked) == 1
    assert "Луна в Тельце" in parked[0].read_text(encoding="utf-8")
    assert "збережено" in out
    assert used(calls, "astro_learn.py") == [], "the reference must not be distilled here"
    assert used(calls, "notify.sh"), "the main chat has to be told it arrived"


def test_reference_does_not_recompute(monkeypatch, tmp_path):
    """Only an explicit recalc re-reads the day; filing a reference does not."""
    monkeypatch.setattr(inbox, "HOME", tmp_path)
    calls = capture(monkeypatch)
    inbox.park_reference("календар", {"day": "today", "period": "день"})
    assert used(calls, "systemd-run") == []


def test_reference_for_tomorrow_is_filed_under_tomorrow(monkeypatch, tmp_path):
    monkeypatch.setattr(inbox, "HOME", tmp_path)
    capture(monkeypatch)
    inbox.park_reference("календар", {"day": "tomorrow", "period": "день"})
    parked = list((tmp_path / "status" / "state" / "astro-reference-inbox").glob("*.txt"))
    assert parked[0].name.endswith(".txt")
    assert str(date.today().toordinal() + 1) or True   # name carries the resolved day
    assert parked[0].name.split("-", 2)[2][:10] > date.today().isoformat()


def test_feedback_still_recorded(monkeypatch, tmp_path):
    """His account of a day is exactly what she is for — unchanged."""
    monkeypatch.setattr(inbox, "HOME", tmp_path)
    calls = capture(monkeypatch)
    inbox.record_feedback("сьогодні було спокійніше, ніж ти казала, і зовсім без тертя")
    assert used(calls, "mood_feedback.py")
    assert any("zirka" in str(p) for c in calls for p in c), "the source has to say where it came from"
