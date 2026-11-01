"""t1119 — the log of what was actually said, and the screen that reads it.

Nothing in this system recorded what it sent. A timer that ran and stayed silent looks
exactly like one that did its job, in `systemctl` and in the journal alike.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))
sys.path.insert(0, str(ROOT / "status" / "tools"))

import render                                                           # noqa: E402
import sent_log                                                         # noqa: E402
import sent_screen                                                      # noqa: E402
import server                                                           # noqa: E402


def write(log, rows):
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")


def row(**kw):
    base = {"ts": "2026-11-01T20:03:00+02:00", "bot": "main", "kind": "digest-headless.sh",
            "ok": True, "codes": {"text": 200, "voice": 200}, "voice": True,
            "chars": 120, "text": "вечірній дайджест"}
    base.update(kw)
    return base


# --- TC1-TC3: the log --------------------------------------------------------------------

def test_a_record_carries_what_the_screen_needs(tmp_path, monkeypatch):
    log = tmp_path / "chat-log.jsonl"
    monkeypatch.setattr(sent_log, "LOG", log)
    sent_log.append(bot="zirka", kind="mood.py", text="прогноз на день",
                    codes={"text": 200, "voice": 200}, voice=True)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert set(rec) >= {"ts", "bot", "kind", "ok", "codes", "voice", "chars", "text"}
    assert rec["bot"] == "zirka" and rec["ok"] is True and rec["chars"] == len("прогноз на день")
    assert "chat" not in rec, "the chat id is personal and belongs in one file only"


@pytest.mark.parametrize("codes,ok", [
    ({"text": 200, "voice": 200}, True),
    ({"text": 200}, True),
    ({"text": 400, "voice": 200}, False),
    ({"text": 200, "voice": 500}, False),
    ({}, False),
])
def test_ok_follows_telegram_not_an_assumption(tmp_path, monkeypatch, codes, ok):
    log = tmp_path / "chat-log.jsonl"
    monkeypatch.setattr(sent_log, "LOG", log)
    sent_log.append(bot="main", kind="x", text="t", codes=codes, voice="voice" in codes)
    assert json.loads(log.read_text(encoding="utf-8"))["ok"] is ok


def test_the_kind_falls_back_to_the_calling_script(tmp_path, monkeypatch):
    """So a digest says `digest-headless.sh` and a reminder says `remind.py` without a
    single caller having to pass anything."""
    log = tmp_path / "chat-log.jsonl"
    monkeypatch.setattr(sent_log, "LOG", log)
    monkeypatch.setattr(sent_log, "caller", lambda: "remind.py")
    sent_log.append(bot="main", kind="", text="t", codes={"text": 200}, voice=False)
    assert json.loads(log.read_text(encoding="utf-8"))["kind"] == "remind.py"


@pytest.mark.parametrize("word", ["/tmp/snapshot-bash-179.sh", "snapshot-bash-1.sh",
                                  "/var/tmp/x.sh", "bash-wrapper.sh"])
def test_a_throwaway_wrapper_is_not_recorded_as_the_sender(word):
    """The terminal harness runs commands through a generated wrapper in /tmp; recording
    that as the kind of a message is noise where a name is expected."""
    assert sent_log._throwaway(word)


@pytest.mark.parametrize("word", ["status/mood.py", "/home/ich/claude-home/status/watch.py",
                                  "remind.py"])
def test_a_real_script_is_recorded(word):
    assert not sent_log._throwaway(word)


def test_the_log_is_trimmed_to_the_newest(tmp_path, monkeypatch):
    log = tmp_path / "chat-log.jsonl"
    monkeypatch.setattr(sent_log, "LOG", log)
    monkeypatch.setattr(sent_log, "max_lines", lambda: 10)
    for i in range(25):
        sent_log.append(bot="main", kind="k", text=f"повідомлення {i}",
                        codes={"text": 200}, voice=False)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 10
    assert json.loads(lines[-1])["text"] == "повідомлення 24", \
        "the line just written must survive the trim"


def test_appending_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sent_log, "LOG", tmp_path / "in-the-way" / "chat-log.jsonl")
    (tmp_path / "in-the-way").write_text("не тека", encoding="utf-8")
    sent_log.append(bot="main", kind="k", text="t", codes={"text": 200}, voice=False)


# --- TC4-TC5: reading it -----------------------------------------------------------------

def test_a_torn_line_is_skipped_and_the_newest_comes_first(tmp_path):
    log = tmp_path / "chat-log.jsonl"
    log.write_text(
        json.dumps(row(ts="2026-11-01T08:03:00+02:00", text="ранковий")) + "\n"
        + '{"ts": "2026-11-01T12:00:00+02:00", "bot": "ma\n'          # torn
        + json.dumps(row(ts="2026-11-01T20:03:00+02:00", text="вечірній")) + "\n",
        encoding="utf-8")
    rows = sent_screen.rows(log)
    assert [r["text"] for r in rows] == ["вечірній", "ранковий"]


def test_an_absent_log_is_an_empty_screen(tmp_path):
    assert sent_screen.rows(tmp_path / "nothing.jsonl") == []
    html = render.render_sent([], {"total": 0, "voice": 0, "failed": 0}, [], [], "", "",
                              bodies=False)
    assert "Ще нічого" in html


def test_the_filters_narrow_by_bot_and_by_kind(tmp_path):
    log = tmp_path / "chat-log.jsonl"
    write(log, [row(bot="main", kind="watch.py", text="вартовий"),
                row(bot="zirka", kind="mood.py", text="прогноз"),
                row(bot="bruno", kind="youtube-headless.sh", text="відео")])
    assert len(sent_screen.rows(log, bot="zirka")) == 1
    assert sent_screen.rows(log, bot="zirka")[0]["text"] == "прогноз"
    assert len(sent_screen.rows(log, kind="watch.py")) == 1
    assert len(sent_screen.rows(log, bot="main", kind="mood.py")) == 0
    assert sorted(sent_screen.bots(sent_screen.rows(log))) == ["bruno", "main", "zirka"]


# --- TC6-TC7: what the screen shows ------------------------------------------------------

def test_the_body_is_hidden_unless_the_setting_says_otherwise(tmp_path):
    rows = [row(text="сьогодні 12:00 поминки, 17:00 день народження")]
    hidden = render.render_sent(rows, sent_screen.counters(rows), ["main"], ["x"], "", "",
                               bodies=False)
    assert "поминки" not in hidden, "a digest's text is the owner's calendar"
    shown = render.render_sent(rows, sent_screen.counters(rows), ["main"], ["x"], "", "",
                               bodies=True)
    assert "поминки" in shown


def test_everything_interpolated_is_escaped(tmp_path):
    rows = [row(kind="<script>alert(1)</script>", text="<b>x</b>")]
    html = render.render_sent(rows, sent_screen.counters(rows), [], [], "", "", bodies=True)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_the_counters_match_the_rows():
    rows = [row(), row(voice=False), row(ok=False, codes={"text": 400})]
    got = sent_screen.counters(rows)
    assert got == {"total": 3, "voice": 2, "failed": 1}


def test_a_failed_message_is_marked():
    rows = [row(ok=False, codes={"text": 400, "voice": 200})]
    html = render.render_sent(rows, sent_screen.counters(rows), [], [], "", "", bodies=False)
    assert "400" in html


# --- TC8: the screen is read-only --------------------------------------------------------

def test_sent_is_no_longer_a_placeholder():
    assert "/sent" not in server.SOON
    assert "/sent" in dict(render.SCREENS)


def test_the_screen_has_no_form():
    html = render.render_sent([row()], {"total": 1, "voice": 1, "failed": 0}, ["main"],
                              ["k"], "", "", bodies=False)
    assert 'method="post"' not in html


# --- the wiring: notify.sh must actually write the log -----------------------------------

def test_notify_sh_appends_to_the_log():
    """The wiring, not the helper: `notify.sh` has to call it, with the codes it got."""
    text = (ROOT / "notify.sh").read_text(encoding="utf-8")
    assert "sent_log.py" in text
    assert "http_code" in text, "the delivery result has to be captured, not assumed"
