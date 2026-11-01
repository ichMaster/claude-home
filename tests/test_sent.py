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
    # Shaped like a calendar line, because that is what must not leak — but invented.
    # The first version of this fixture reproduced an actual line out of the owner's own
    # digest, which has no business in a public repository (t1120).
    rows = [row(text="завтра 09:30 техогляд, 18:00 вечеря з Х")]
    hidden = render.render_sent(rows, sent_screen.counters(rows), ["main"], ["x"], "", "",
                               bodies=False)
    assert "техогляд" not in hidden, "a digest's text is the owner's calendar"
    shown = render.render_sent(rows, sent_screen.counters(rows), ["main"], ["x"], "", "",
                               bodies=True)
    assert "техогляд" in shown


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


# --- t1121: the failure the log exists for (phase-9 review H1, M1-M5) --------------------

SHIM = '''#!/bin/bash
# a curl that answers the way the stubs say, including failing like a network does
if [ -n "${STUB_FAIL:-}" ]; then echo "curl: stubbed network error" >&2; exit "$STUB_FAIL"; fi
case "$*" in
  *sendVoice*) [ -n "${STUB_VOICE_FAIL:-}" ] && { echo "curl: boom" >&2; exit "$STUB_VOICE_FAIL"; }
               printf '%s' "${STUB_VOICE_CODE:-200}" ;;
  *) [ -n "${STUB_TEXT_FAIL:-}" ] && { echo "curl: boom" >&2; exit "$STUB_TEXT_FAIL"; }
     printf '%s' "${STUB_TEXT_CODE:-200}" ;;
esac
'''


@pytest.fixture
def offline(tmp_path):
    """`notify.sh` with every outward call stubbed: no Telegram, no ElevenLabs, no network.

    The wiring used to be "tested" by grepping notify.sh for two substrings, which is how
    H1, M1 and M2 all survived the suite (phase-9 review M5).
    """
    home = tmp_path / "home"
    repo = home / "claude-home"
    (repo / "voice").mkdir(parents=True)
    (repo / "status" / "tools").mkdir(parents=True)
    (repo / "status" / "state").mkdir(parents=True)
    for name in ("notify.sh", "config.sh", "config.json"):
        (repo / name).write_bytes((ROOT / name).read_bytes())
    (repo / "notify.sh").chmod(0o755)
    (repo / "status" / "tools" / "sent_log.py").write_bytes(
        (ROOT / "status" / "tools" / "sent_log.py").read_bytes())
    (repo / "noosconf.py").write_bytes((ROOT / "noosconf.py").read_bytes())
    (repo / ".env.telegram").write_text(
        "TELEGRAM_BOT_TOKEN=stub\nTELEGRAM_CHAT_ID=1\n", encoding="utf-8")
    (repo / "voice" / "el_say.sh").write_text(
        '#!/bin/bash\n[ -n "${STUB_EL_FAIL:-}" ] && exit "$STUB_EL_FAIL"\n'
        'printf x > "$1"\n', encoding="utf-8")
    (repo / "voice" / "el_say.sh").chmod(0o755)
    (repo / "voice" / "to_ogg.py").write_text("import sys, pathlib\n"
                                              "pathlib.Path(sys.argv[2]).write_text('x')\n",
                                              encoding="utf-8")
    venv = repo / ".venv-voice" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(sys.executable)
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "curl").write_text(SHIM, encoding="utf-8")
    (shim / "curl").chmod(0o755)
    return repo, shim


def run_notify(offline, args, **stubs):
    repo, shim = offline
    env = dict(os.environ)
    env.update({"HOME": str(repo.parent), "PATH": f"{shim}:{env['PATH']}"})
    env.update({k: str(v) for k, v in stubs.items()})
    out = subprocess.run(["./notify.sh", *args], cwd=str(repo), env=env,
                         capture_output=True, text=True, timeout=120)
    log = repo / "status" / "state" / "chat-log.jsonl"
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()
            if x.strip()] if log.exists() else []
    return out, rows


def test_a_refused_message_is_recorded(offline):
    out, rows = run_notify(offline, ["--no-voice", "x"], STUB_TEXT_CODE=400)
    assert rows and rows[0]["ok"] is False and rows[0]["codes"]["text"] == 400


def test_a_transport_failure_is_recorded(offline):
    """H1: `code=$(curl …)` under `set -e` aborted the script before the log, so the most
    likely failure of all — Telegram unreachable — was the one the log could not show."""
    out, rows = run_notify(offline, ["--no-voice", "z"], STUB_TEXT_FAIL=28)
    assert rows, "a message that never left must still be recorded"
    assert rows[0]["ok"] is False
    assert rows[0].get("error"), "and it must say it was a transport failure, not a refusal"


def test_a_delivered_text_survives_a_failed_voice_call(offline):
    """H1's second half: the text went out, the voice call could not connect, and the whole
    record — including the delivered part — disappeared."""
    out, rows = run_notify(offline, ["w"], STUB_VOICE_FAIL=7)
    assert rows and rows[0]["codes"].get("text") == 200
    assert rows[0]["ok"] is False and rows[0].get("error")


def test_a_refused_synthesis_is_recorded(offline):
    out, rows = run_notify(offline, ["v"], STUB_EL_FAIL=1)
    assert rows and rows[0]["codes"].get("text") == 200 and rows[0]["ok"] is False


def test_one_message_makes_exactly_one_record(offline):
    out, rows = run_notify(offline, ["ok-path"])
    assert len(rows) == 1 and rows[0]["ok"] is True
    assert rows[0]["codes"] == {"text": 200, "voice": 200}


def test_the_kind_comes_from_the_environment_when_a_model_sends(offline):
    """M1: four units send through `claude -p`, where the parent is a harness shell and the
    script name is nowhere in the tree. The wrappers export NOOS_SENT_KIND instead."""
    out, rows = run_notify(offline, ["--no-voice", "x"],
                           NOOS_SENT_KIND="digest-headless.sh")
    assert rows[0]["kind"] == "digest-headless.sh"


def test_an_explicit_kind_wins_over_the_environment(offline):
    out, rows = run_notify(offline, ["--kind", "ручне", "--no-voice", "x"],
                           NOOS_SENT_KIND="digest-headless.sh")
    assert rows[0]["kind"] == "ручне"


def test_the_bot_recorded_is_the_bot_used(offline):
    """M2: on the token fallback the record named a chat the message never reached — and the
    chat id was dropped on the strength of that field."""
    out, rows = run_notify(offline, ["--bot", "nonexistent", "--no-voice", "x"])
    assert rows[0]["bot"] == "main"
    assert rows[0].get("asked") == "nonexistent", "and it says what was asked for"


def test_the_headless_wrappers_name_their_kind():
    """The four model-driven senders, where the fallback cannot work."""
    for name in ("digest-headless.sh", "youtube-headless.sh", "social-headless.sh",
                 "code-review-headless.sh"):
        text = (ROOT / "status" / name).read_text(encoding="utf-8")
        assert "NOOS_SENT_KIND" in text, name


def test_concurrent_appends_at_the_cap_lose_nothing(tmp_path, monkeypatch):
    """M3: the trim is a read-modify-write, and 11-15 of 20 records vanished."""
    import threading
    log = tmp_path / "chat-log.jsonl"
    monkeypatch.setattr(sent_log, "LOG", log)
    monkeypatch.setattr(sent_log, "max_lines", lambda: 10)
    monkeypatch.setattr(sent_log, "caller", lambda: "t")

    def write(i):
        sent_log.append(bot="main", kind="k", text=f"м{i}", codes={"text": 200},
                        voice=False)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()
             if x.strip()]
    assert len(lines) == 10, f"{len(lines)} lines kept"
    assert all(json.dumps(r, ensure_ascii=False) for r in lines), "every line parses"


def test_a_filter_link_survives_a_hostile_kind():
    """M4: the links were escaped for HTML and not encoded for a URL, so the screen's own
    link answered «ще нічого» about a record that exists."""
    rows = [row(kind="a&b+c#d")]
    html = render.render_sent(rows, sent_screen.counters(rows), ["main"], ["a&b+c#d"],
                              "", "", bodies=False)
    assert "a%26b%2Bc%23d" in html


def test_a_record_of_the_wrong_shape_does_not_down_the_screen():
    """Low, but the screen must not 500 on a line it does not understand."""
    rows = [{"ts": 12345, "bot": None, "codes": "200", "chars": "кілька"}]
    html = render.render_sent(rows, {"total": 1, "voice": 0, "failed": 0}, [], [], "",
                              "", bodies=True)
    assert "Надіслане" in html


def test_the_log_is_created_private(tmp_path, monkeypatch):
    """It holds the text of every message sent — the most personal file in status/state."""
    log = tmp_path / "chat-log.jsonl"
    monkeypatch.setattr(sent_log, "LOG", log)
    monkeypatch.setattr(sent_log, "caller", lambda: "t")
    sent_log.append(bot="main", kind="k", text="t", codes={"text": 200}, voice=False)
    assert oct(log.stat().st_mode & 0o777) == "0o600"
