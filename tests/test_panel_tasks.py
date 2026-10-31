"""t1074 — admin panel, phase 6. The board writes through store.py, so the tests are
about which column a task lands in and which verb a button runs.
"""
import subprocess
import sys
import types
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import render                                                           # noqa: E402
import server                                                           # noqa: E402
import tasks_screen as ts                                               # noqa: E402

TODAY = date(2026, 10, 31)

STATE = {
    "t1": {"title": "прострочена", "status": "open", "due": "2026-10-25", "estimate": 30},
    "t2": {"title": "на сьогодні", "status": "open", "due": "2026-10-31", "block": True},
    "t3": {"title": "на вихідні", "status": "open", "due": None,
           "period": ["вихідні", "2026-10-31", "2026-11-01"]},
    "t4": {"title": "беклог", "status": "open", "due": None, "period": None},
    "t5": {"title": "закрита", "status": "done", "closed": "2026-10-31T10:00:00+02:00"},
    "t6": {"title": "закрита давно", "status": "done", "closed": "2026-01-01T10:00:00+02:00"},
    "t7": {"title": "і дата, і період", "status": "open", "due": "2026-10-20",
           "period": ["тиждень", "2026-10-26", "2026-11-01"]},
}


# --- TC1: columns ---------------------------------------------------------------------

def test_each_task_lands_in_one_column():
    cols = ts.columns(STATE, TODAY)
    assert [c["id"] for c in cols["today"]] == ["t7", "t1", "t2"]
    assert [c["id"] for c in cols["period"]] == ["t3"]
    assert [c["id"] for c in cols["backlog"]] == ["t4"]
    assert [c["id"] for c in cols["closed"]] == ["t5"], "an old closure is not today's work"


def test_overdue_comes_first_and_is_flagged():
    cols = ts.columns(STATE, TODAY)
    assert cols["today"][0]["overdue"] is True
    assert cols["today"][-1]["overdue"] is False


def test_a_date_outranks_a_period():
    """A card in two columns gets done twice or not at all."""
    cols = ts.columns(STATE, TODAY)
    ids = [c["id"] for col in cols.values() for c in col]
    assert ids.count("t7") == 1


# t1077 — the board's own «завтра» button creates a future-dated task; it must land in
# «Період» (scheduled for later), not read as demoted into «Беклог».

def test_a_future_date_is_period_not_backlog():
    state = dict(STATE)
    state["t8"] = {"title": "на завтра перенесена", "status": "open", "due": "2026-11-01"}
    cols = ts.columns(state, TODAY)
    assert "t8" in [c["id"] for c in cols["period"]]
    assert "t8" not in [c["id"] for c in cols["backlog"]]


def test_period_column_sorts_by_what_starts_sooner():
    state = {
        "a": {"title": "дата пізня", "status": "open", "due": "2026-11-09"},
        "b": {"title": "вікенд", "status": "open",
              "period": ["вихідні", "2026-11-07", "2026-11-08"]},
        "c": {"title": "дата рання", "status": "open", "due": "2026-11-02"},
    }
    cols = ts.columns(state, TODAY)
    assert [c["id"] for c in cols["period"]] == ["c", "b", "a"]


def test_a_malformed_period_does_not_crash_the_board():
    """L2 hardening: a hand-written one-element period must not blank the whole screen."""
    state = {"x": {"title": "крива", "status": "open", "period": ["вихідні"]},
             "y": {"title": "ціла", "status": "open",
                   "period": ["тиждень", "2026-11-02", "2026-11-08"]}}
    cols = ts.columns(state, TODAY)
    assert {c["id"] for c in cols["period"]} == {"x", "y"}


# --- TC2: what a card shows ---------------------------------------------------------------

def test_card_reports_spent_and_running():
    now = datetime.now().astimezone()
    t = {"title": "йде", "status": "open",
         "runs": [{"from": (now - timedelta(minutes=40)).isoformat(), "to": None}],
         "running": True}
    c = ts.card("t9", t, TODAY)
    assert c["running"] is True and 39 <= c["spent"] <= 41


def test_card_separates_plan_from_fact():
    t = {"title": "з подіями", "status": "open", "events": [
        {"event": "a", "start": "2026-10-31T10:00", "end": "", "kind": "plan"},
        {"event": "b", "start": "2026-10-31T14:00", "end": "", "kind": "fact"}]}
    c = ts.card("t9", t, TODAY)
    assert [e["event"] for e in c["plan"]] == ["a"]
    assert [e["event"] for e in c["fact"]] == ["b"]


def test_card_survives_a_broken_run_entry():
    t = {"title": "крива", "status": "open", "runs": [{"from": "не дата", "to": None}]}
    assert ts.card("t9", t, TODAY)["spent"] == 0


def test_period_is_readable():
    assert ts.period_text(["вихідні", "2026-10-31", "2026-11-01"]) == "вихідні 31.10-01.11"
    assert ts.period_text(None) == ""


# --- TC3, TC4: the actions ------------------------------------------------------------------

def runs(monkeypatch):
    seen = []

    def run(cmd, **kw):
        seen.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stdout="зроблено", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    return seen


def store_call(seen):
    return [c for c in seen if any(str(p).endswith("store.py") for p in c)][0]


def test_close_runs_done(monkeypatch):
    seen = runs(monkeypatch)
    server.tasks_action({"action": ["done"], "id": ["t1"]})
    cmd = store_call(seen)
    assert cmd[-2:] == ["done", "t1"]


def test_defer_passes_the_phrase(monkeypatch):
    seen = runs(monkeypatch)
    server.tasks_action({"action": ["defer"], "id": ["t1"], "when": ["завтра"]})
    cmd = store_call(seen)
    assert cmd[-3:] == ["defer", "t1", "завтра"]


def test_block_toggles(monkeypatch):
    seen = runs(monkeypatch)
    server.tasks_action({"action": ["block"], "id": ["t2"], "on": ["off"]})
    assert store_call(seen)[-3:] == ["block", "t2", "off"]


def test_add_passes_the_text_as_one_argument(monkeypatch):
    seen = runs(monkeypatch)
    server.tasks_action({"action": ["add"], "text": ["помити машину завтра"]})
    cmd = store_call(seen)
    assert cmd[-2:] == ["add", "помити машину завтра"]


def test_empty_add_runs_nothing(monkeypatch):
    seen = runs(monkeypatch)
    msg = server.tasks_action({"action": ["add"], "text": ["   "]})
    assert seen == [] and "порожн" in msg.lower()


def test_unknown_action_changes_nothing(monkeypatch):
    seen = runs(monkeypatch)
    msg = server.tasks_action({"action": ["вигадана"], "id": ["t1"]})
    assert seen == [] and "невідом" in msg.lower()


def test_run_script_returns_an_exec_failure_instead_of_raising(monkeypatch):
    """t1079: E2BIG on a huge add text (or a missing interpreter) must become a message
    on the board, not the handler's bare 500."""
    def boom(*a, **kw):
        raise OSError(7, "Argument list too long")
    monkeypatch.setattr(subprocess, "run", boom)
    ok, said = server.run_script("/bin/echo", "x")
    assert ok is False and "не вдалося запустити" in said


def test_action_without_an_id_runs_nothing(monkeypatch):
    seen = runs(monkeypatch)
    msg = server.tasks_action({"action": ["done"], "id": [""]})
    assert seen == [] and msg


# --- t1078: refresh must not re-fire the last action (Post/Redirect/Get) ---------------

@pytest.fixture
def live_panel(monkeypatch):
    """The real handler on a real socket; the action and the board are stubbed so no
    subprocess runs and the real log is never read."""
    import threading
    from http.server import ThreadingHTTPServer
    fired = []

    def fake_action(form):
        fired.append(form.get("action"))
        return "зроблено ✔"
    monkeypatch.setattr(server, "tasks_action", fake_action)
    monkeypatch.setattr(server, "tasks_html",
                        lambda message="": f"<html>дошка: {message}</html>")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], fired
    httpd.shutdown()


def post_tasks(port, body):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/tasks", urllib.parse.urlencode(body),
                 {"Content-Type": "application/x-www-form-urlencoded"})
    return conn, conn.getresponse()


def test_post_redirects_so_refresh_cannot_rewrite(live_panel):
    """TC1+TC2: the page left in the browser must be a GET, never the form submission."""
    port, fired = live_panel
    conn, r = post_tasks(port, {"token": server.FORM_TOKEN,
                                "action": "add", "text": "нова"})
    assert r.status == 303, "a 200 here means F5 re-fires the action into the log"
    location = r.getheader("Location")
    assert location and location.startswith("/tasks?m=")
    r.read()
    assert fired == [["add"]]
    conn.request("GET", location)
    shown = conn.getresponse().read().decode("utf-8")
    assert "зроблено ✔" in shown, "the action's message must survive the redirect"
    assert fired == [["add"]], "the GET after the redirect must not act"


def test_post_without_the_token_is_still_refused(live_panel):
    port, fired = live_panel
    conn, r = post_tasks(port, {"action": "done", "id": "t1"})
    assert r.status == 403 and fired == []


# --- TC5, TC6: the page -------------------------------------------------------------------------

def test_page_escapes_titles_and_carries_the_token():
    cols = ts.columns({"t1": {"title": "<img src=x onerror=bad()>", "status": "open",
                              "due": "2026-10-31", "project": "<b>p</b>"}}, TODAY)
    html = render.render_tasks(cols, token="SECRET", message="")
    assert "<img src=x" not in html and "<b>p</b>" not in html
    assert "&lt;img src=x" in html
    assert html.count('name="token" value="SECRET"') >= 2
