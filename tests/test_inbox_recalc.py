"""t1033 — a reference about today recomputes today, and a second request while one run is
in flight does not start a second pipeline.
"""
import subprocess
import types
from datetime import date, datetime, timedelta

import inbox


def fake_run(monkeypatch, calls, learn_rc=0, systemd_rc=0, systemd_err=""):
    """Capture subprocess.run: astro_learn.py and systemd-run are the two callers here."""
    def run(cmd, **kw):
        calls.append(cmd)
        if any("astro_learn.py" in str(c) for c in cmd):
            return types.SimpleNamespace(returncode=learn_rc, stdout="ПРАВИЛО: щось",
                                         stderr="")
        return types.SimpleNamespace(returncode=systemd_rc, stdout="", stderr=systemd_err)
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def systemd_calls(calls):
    return [c for c in calls if c and c[0] == "systemd-run"]


def test_reference_for_today_recomputes(monkeypatch):
    """TC4: a reading about today has to change today, not only tomorrow morning."""
    calls = fake_run(monkeypatch, [])
    out = inbox.take_reference("календар", {"day": "today", "period": "день"})
    assert "Перерахунок" in out
    started = systemd_calls(calls)
    assert len(started) == 1
    assert "--day" in started[0]
    assert started[0][started[0].index("--day") + 1] == date.today().isoformat()


def test_reference_for_tomorrow_does_not_recompute(monkeypatch):
    """TC4: tomorrow's reading is stored and learned from; nothing is re-run."""
    calls = fake_run(monkeypatch, [])
    out = inbox.take_reference("календар", {"day": "tomorrow", "period": "день"})
    assert "Перерахунок" not in out
    assert systemd_calls(calls) == []


def test_second_recalc_while_running_is_refused(monkeypatch):
    """TC5: the unit name is the lock — a run already in flight is reported, not duplicated."""
    fake_run(monkeypatch, [], systemd_rc=1,
             systemd_err="Failed to start transient service unit: Unit "
                         "noos-mood-recalc.service already exists.")
    assert inbox.recompute_forecast(date.today()) == "перерахунок уже йде"


def test_failed_start_is_reported_not_swallowed(monkeypatch):
    """A recalculation that could not start must not read as if it had."""
    fake_run(monkeypatch, [], systemd_rc=1, systemd_err="D-Bus недоступний")
    out = inbox.recompute_forecast(date.today())
    assert out.startswith("перерахунок не запустився")
    assert "D-Bus" in out
