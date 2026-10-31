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


def test_recalc_runs_for_the_day_asked_for(monkeypatch):
    """Asked from her chat, the day is re-read — the point of t1033, so he never has to
    reach a terminal for it."""
    calls = fake_run(monkeypatch, [])
    out = inbox.recompute_forecast(date.today())
    assert "перерахунок запущено" in out
    started = systemd_calls(calls)
    assert len(started) == 1
    assert started[0][started[0].index("--day") + 1] == date.today().isoformat()


# A reference used to trigger this too (t1033). t1059 took that away: references are
# parked and calibration happens through the session, so only an explicit request
# re-reads the day. That is covered in tests/test_inbox_reference.py.


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
