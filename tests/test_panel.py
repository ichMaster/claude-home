"""t1055 — admin panel, phase 1. Read-only, so the tests are about reading correctly:
staleness, systemctl output, state files, escaping, and that /static cannot be escaped.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "panel"))

import data                                                             # noqa: E402
import render                                                           # noqa: E402
import server                                                           # noqa: E402

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def probe(**kw):
    return {"id": "loe", "ok": True, "severity": "info", "ttl": 600,
            "text": "Світло є", **kw}


# --- TC1, TC2: probes -------------------------------------------------------------------

def test_stale_when_older_than_its_own_ttl():
    fresh = probe(checked=(NOW - timedelta(seconds=60)).isoformat())
    old = probe(checked=(NOW - timedelta(seconds=3600)).isoformat())
    rows = data.probe_rows([fresh, old], NOW)
    assert rows[0]["stale"] is False
    assert rows[1]["stale"] is True


def test_unknown_age_is_stale_not_fresh():
    """An answer with no timestamp must not be rendered as current."""
    assert data.probe_rows([probe()], NOW)[0]["stale"] is True
    assert data.probe_rows([probe(checked="не дата")], NOW)[0]["stale"] is True


def test_severity_drives_the_mark_and_unknown_does_not_raise():
    rows = data.probe_rows([probe(severity="alert"), probe(severity="whatever")], NOW)
    assert rows[0]["css"] == "alert"
    assert rows[1]["css"] == "quiet" and rows[1]["mark"] == "·"


def test_multiline_probe_text_is_one_line():
    rows = data.probe_rows([probe(text="Пошта: 3 нових\n  • хтось: тема")], NOW)
    assert rows[0]["text"] == "Пошта: 3 нових"


# --- TC3: timers ------------------------------------------------------------------------

TIMER = ("Unit=noos-digest.service\n"
         "NextElapseUSecRealtime=Sat 2026-10-31 20:03:00 EET\n"
         "LastTriggerUSec=Sat 2026-10-31 08:03:00 EET\n"
         "ActiveState=active\n")
SERVICE_OK = "Result=success\nExecMainStatus=0\nActiveState=inactive\n"
SERVICE_BAD = "Result=exit-code\nExecMainStatus=1\nActiveState=failed\n"


def test_timer_row_reads_the_properties():
    row = data.timer_rows([("noos-digest.timer", TIMER, SERVICE_OK)])[0]
    assert row["next"].endswith("20:03:00 EET")
    assert row["failed"] is False and row["enabled"] is True


def test_timer_failure_is_visible():
    row = data.timer_rows([("noos-digest.timer", TIMER, SERVICE_BAD)])[0]
    assert row["failed"] is True and row["result"] == "exit-code" and row["exit"] == "1"


def test_timer_that_never_ran_says_so():
    never = TIMER.replace("LastTriggerUSec=Sat 2026-10-31 08:03:00 EET",
                          "LastTriggerUSec=n/a")
    row = data.timer_rows([("noos-subs.timer", never, "")])[0]
    assert row["last"] == "не запускався" and row["failed"] is False


def test_unreadable_properties_give_blanks_not_an_exception():
    row = data.timer_rows([("noos-x.timer", "", "")])[0]
    assert row["unit"] == "noos-x.timer" and row["next"] == ""


# --- TC4: queues ------------------------------------------------------------------------

def test_queues_from_state(tmp_path):
    (tmp_path / "youtube.json").write_text(json.dumps(
        {"pending": [1, 2, 3], "seen": ["a"], "blocked_until": "2026-10-31T09:00:00+00:00"}))
    (tmp_path / "mail.json").write_text(json.dumps({"last_uid": 42, "checked": "2026-10-31T08:00:00"}))
    (tmp_path / "watch.json").write_text(json.dumps(
        {"loe": {"sev": "warn"}, "alarm": {"sev": "info"}, "host": {"sev": "alert"}}))
    q = data.queues(tmp_path)
    assert q["youtube_pending"] == 3 and q["mail_last_uid"] == 42
    assert q["watch_loud"] == ["host", "loe"]


def test_queues_on_a_fresh_machine(tmp_path):
    """A fresh machine has no state files. A count of nothing is 0; a UID nobody has read
    yet is **unknown**, and this test used to assert the wrong one of those (t1114)."""
    q = data.queues(tmp_path)
    assert q["youtube_pending"] == 0 and q["mail_last_uid"] is None and q["watch_loud"] == []


def test_queues_survive_a_torn_state_file(tmp_path):
    (tmp_path / "youtube.json").write_text('{"pending": [1,')
    assert data.queues(tmp_path)["youtube_pending"] == 0


# --- TC5: the change log ------------------------------------------------------------------

def test_recent_changes_newest_first_and_skips_a_torn_line(tmp_path):
    (tmp_path / "2026-10-30.jsonl").write_text(
        json.dumps({"ts": "2026-10-30T10:00:00", "kind": "edit", "target": "a"}) + "\n",
        encoding="utf-8")
    (tmp_path / "2026-10-31.jsonl").write_text(
        json.dumps({"ts": "2026-10-31T09:00:00", "kind": "write", "target": "b"}) + "\n"
        + '{"ts": "2026-10-31T09:30:00", "kind": "bas\n'
        + json.dumps({"ts": "2026-10-31T10:00:00", "kind": "bash", "target": "c"}) + "\n",
        encoding="utf-8")
    rows = data.recent_changes(10, tmp_path)
    assert [r["target"] for r in rows] == ["c", "b", "a"]


def test_recent_changes_empty_dir(tmp_path):
    assert data.recent_changes(10, tmp_path) == []
    assert data.recent_changes(10, tmp_path / "missing") == []


def test_recent_changes_respects_the_limit(tmp_path):
    (tmp_path / "2026-10-31.jsonl").write_text("".join(
        json.dumps({"ts": f"2026-10-31T10:00:{i:02d}", "kind": "bash", "target": str(i)}) + "\n"
        for i in range(30)), encoding="utf-8")
    assert len(data.recent_changes(5, tmp_path)) == 5


# --- TC6: rendering -----------------------------------------------------------------------

def test_probe_text_is_escaped():
    """A mail subject reaches the probe text, and a subject is written by the sender."""
    rows = data.probe_rows([probe(text='<img src=x onerror="alert(1)">')], NOW)
    html = render.render_pulse(rows, [], data.queues(Path("/nonexistent")), [])
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_change_log_detail_is_escaped():
    html = render.render_pulse([], [], data.queues(Path("/nonexistent")),
                               [{"ts": "2026-10-31T10:00:00", "kind": "bash",
                                 "target": "rm", "detail": "<script>bad()</script>"}])
    assert "<script>bad()" not in html


def test_pulse_has_every_section_and_one_row_per_probe():
    rows = data.probe_rows([probe(id="loe"), probe(id="alarm")], NOW)
    html = render.render_pulse(rows, data.timer_rows([("noos-digest.timer", TIMER, SERVICE_OK)]),
                               data.queues(Path("/nonexistent")), [])
    for heading in ("Пробники", "Таймери", "Черги", "Останні зміни"):
        assert heading in html
    assert html.count('<td class="id">loe</td>') == 1
    assert 'class="rail"' in html


def test_age_text_reads_in_ukrainian():
    assert data.probe_rows([probe()], NOW)[0]["age"] is None
    assert "хв тому" in render.age_text(300, 600)
    assert render.age_text(None, 600) == "невідомо коли"


# --- TC7: routing -------------------------------------------------------------------------

def test_static_serves_the_stylesheet():
    found = server.static_file("panel.css")
    assert found and found[1].startswith("text/css")
    assert b"--amber" in found[0]


@pytest.mark.parametrize("attack", [
    "../../.env.voice", "../server.py", "/etc/passwd", "..%2f..%2fconfig.local.json"])
def test_static_cannot_escape_its_directory(attack):
    """No authentication guards this port, so traversal here would hand out the keys."""
    assert server.static_file(attack) is None


def test_no_screen_is_a_placeholder_any_more():
    """Phase 9 built the last one (t1119). The placeholder renderer stays — it is how a
    future screen announces itself — but nothing points at it now."""
    assert server.SOON == {}
    for href, _name in render.SCREENS:
        assert href not in server.SOON
    html = render.render_soon("Колись", "/somewhere", "фаза 12")
    assert "фаза 12" in html and "Колись" in html


# --- t1056: probes_now stamps `checked` from the cache mtime --------------------------------
# No probe JSON carries a timestamp — run.sh keys freshness off the cache file's mtime, so
# the panel must read the same clock or every probe renders «невідомо коли / застаріле».

def run_returning(payload):
    def fake_run(*args, **kwargs):
        class R:
            stdout = json.dumps(payload, ensure_ascii=False)
        return R()
    return fake_run


def test_probes_now_takes_the_age_from_the_cache_file(tmp_path, monkeypatch):
    import os
    import time
    payload = [{"id": "loe", "ok": True, "severity": "info", "text": "Світло є", "ttl": 900},
               {"id": "alarm", "ok": True, "severity": "info", "text": "Тиша", "ttl": 60}]
    monkeypatch.setattr(data.subprocess, "run", run_returning(payload))
    cached = tmp_path / "loe.json"
    cached.write_text("{}")
    ten_min_ago = time.time() - 600
    os.utime(cached, (ten_min_ago, ten_min_ago))

    rows = data.probe_rows(data.probes_now(["loe", "alarm"], cache_dir=tmp_path))
    loe = next(r for r in rows if r["id"] == "loe")
    alarm = next(r for r in rows if r["id"] == "alarm")
    assert loe["age"] is not None and 550 <= loe["age"] <= 700
    assert loe["stale"] is False                       # 10 min old against a 15 min TTL
    assert alarm["age"] is None and alarm["stale"] is True   # no cache file → unknown age


def test_probes_now_maps_a_colon_id_to_its_cache_name(tmp_path, monkeypatch):
    payload = [{"id": "news:світ", "ok": True, "severity": "info", "text": "…", "ttl": 600}]
    monkeypatch.setattr(data.subprocess, "run", run_returning(payload))
    (tmp_path / "news-світ.json").write_text("{}")
    assert data.probes_now(["news:світ"], cache_dir=tmp_path)[0].get("checked")


# --- t1057: one dead collector must not blank the whole page --------------------------------
# run.sh has no internal timeout and several probes fetch the network; a hanging upstream
# used to turn the whole page into «500 panel error» instead of one empty section.

@pytest.mark.parametrize("exc", [
    lambda: data.subprocess.TimeoutExpired(cmd="x", timeout=1),
    lambda: OSError("no such file"),
])
def test_collectors_degrade_instead_of_raising(monkeypatch, exc):
    def boom(*args, **kwargs):
        raise exc()
    monkeypatch.setattr(data.subprocess, "run", boom)
    assert data.probes_now(["loe"]) == []
    assert data.timer_units() == []
    assert data.show("noos-x.timer", "Unit") == ""


def test_the_board_renders_with_every_collector_empty():
    html = render.render_pulse([], [], data.queues(Path("/nonexistent")), [])
    for heading in ("Пробники", "Таймери", "Черги", "Останні зміни"):
        assert heading in html
    assert "Пробники не відповіли" in html and "Таймерів не знайдено" in html


# --- t1058: where the panel listens ---------------------------------------------------

def test_resolve_host_passes_a_literal_address_through():
    assert server.resolve_host("127.0.0.1") == "127.0.0.1"
    assert server.resolve_host("0.0.0.0") == "0.0.0.0"


def test_resolve_host_asks_tailscale(monkeypatch):
    """`tailscale` is resolved at start, never written into the config: a hardcoded tailnet
    IP becomes a unit that will not boot the day the address changes."""
    import types
    monkeypatch.setattr(server.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(
                            returncode=0, stdout="100.96.66.17\n", stderr=""))
    assert server.resolve_host("tailscale") == "100.96.66.17"


def test_resolve_host_falls_back_to_loopback(monkeypatch):
    """Tailscale down must not keep the panel from starting — it listens somewhere safe."""
    def boom(*a, **k):
        raise OSError("tailscale not installed")
    monkeypatch.setattr(server.subprocess, "run", boom)
    assert server.resolve_host("tailscale") == "127.0.0.1"


# --- t1114: Pulse must not state what is no longer so (full review: truth M3, M4, M5) ----

def test_an_expired_youtube_pause_is_not_shown_as_current(tmp_path):
    """M3: the pause was rendered in amber 44 minutes after it had expired."""
    past = "2026-11-01T08:44:00+00:00"
    (tmp_path / "youtube.json").write_text(
        json.dumps({"blocked_until": past, "pending": [], "seen": []}), encoding="utf-8")
    q = data.queues(tmp_path, now=datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc))
    assert q["youtube_blocked"] == "", "an expired pause is not a pause"
    q2 = data.queues(tmp_path, now=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc))
    assert q2["youtube_blocked"] == past


def test_an_absent_mail_state_is_unknown_not_zero(tmp_path):
    """M4: «останній UID 0» read as a fact about the mailbox; there was no state file."""
    q = data.queues(tmp_path)
    assert q["mail_last_uid"] is None
    html = render.render_pulse([], [], q, [], 0)
    assert "UID 0" not in html and "невідомо" in html


def test_a_known_mail_uid_is_still_shown(tmp_path):
    (tmp_path / "mail.json").write_text(json.dumps({"last_uid": 4821}), encoding="utf-8")
    assert data.queues(tmp_path)["mail_last_uid"] == 4821


def test_a_run_still_in_flight_is_not_called_successful():
    """M5: `Result=success` is the *previous* run's result while the next one is going —
    worst on the eight-minute forecast and the digest."""
    row = data.timer_rows([("noos-mood.timer",
                            "LastTriggerUSec=Sun 2026-11-01 08:15:00 EET\n",
                            "Result=success\nActiveState=activating\n")])[0]
    assert row["running"] and not row["failed"]
    html = render.render_pulse([], [row], data.queues(Path("/nonexistent")), [], 0)
    assert "виконується" in html and "успішно" not in html


def test_a_finished_run_still_reads_as_successful():
    row = data.timer_rows([("noos-mood.timer",
                            "LastTriggerUSec=Sun 2026-11-01 08:15:00 EET\n",
                            "Result=success\nActiveState=inactive\n")])[0]
    assert not row["running"]
    assert "успішно" in render.render_pulse([], [row], data.queues(Path("/nonexistent")),
                                            [], 0)
