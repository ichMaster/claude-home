"""t1041 — a failure while processing one update must not abort poll() before save_state:
the offset has to be committed so already-sent replies are never re-sent two minutes later."""
import json
import subprocess

import pytest

import inbox


@pytest.fixture
def bot_env(monkeypatch, tmp_path):
    """Offline poll(): fake token/owner, state under tmp, no network, no subprocesses."""
    monkeypatch.setattr(inbox, "STATE", tmp_path)
    monkeypatch.setattr(inbox, "env_telegram", lambda: {
        "TELEGRAM_BOT_TOKEN_ZIRKA": "t", "TELEGRAM_BOT_TOKEN_BRUNO": "t",
        "TELEGRAM_CHAT_ID": "42"})
    monkeypatch.setattr(inbox, "answer", lambda *a, **k: "відповідь")
    monkeypatch.setattr(inbox, "send", lambda *a, **k: None)
    monkeypatch.setattr(inbox, "zirka_kind", lambda *a, **k: {"kind": "chat"})
    monkeypatch.setattr(inbox, "record_feedback", lambda *a, **k: None)
    return tmp_path


def upd(uid, **msg):
    return {"update_id": uid, "message": {"chat": {"id": 42}, "from": {"id": 42}, **msg}}


def test_save_state_is_atomic(monkeypatch, bot_env):
    """t1130: a SIGKILL or power cut mid-write used to truncate <bot>.json; load_state then
    fell back to offset 0 and the next run re-answered the whole last batch. The state must
    go through a temp file + rename, so the file on disk is always one valid JSON."""
    inbox.save_state("zirka", {"offset": 7, "history": [], "answers": []})

    seen = []
    import os as _os
    orig = _os.replace

    def spying_replace(src, dst):
        # at the moment of the rename, the TARGET must still hold the old, valid state:
        # that is the whole point of writing beside it first
        if str(dst).endswith("zirka.json"):
            seen.append(json.loads(inbox.state_file("zirka").read_text(encoding="utf-8")))
        return orig(src, dst)

    monkeypatch.setattr(_os, "replace", spying_replace)
    inbox.save_state("zirka", {"offset": 8, "history": [], "answers": []})
    assert seen, "save_state must write via a temp file + os.replace, not in place"
    assert seen[0]["offset"] == 7, "the old state must stay whole until the rename"
    assert inbox.load_state("zirka")["offset"] == 8


def test_save_state_round_trips(bot_env):
    inbox.save_state("bruno", {"offset": 3, "history": list(range(50)), "answers": []})
    got = inbox.load_state("bruno")
    assert got["offset"] == 3
    assert len(got["history"]) <= 12, "history stays capped"


def test_failing_update_does_not_lose_offset(monkeypatch, bot_env):
    """TC1: update 1 crashes in transcribe, update 2 is plain text — poll() must answer
    update 2 and persist an offset past both, instead of raising and replaying the batch."""
    updates = [upd(100, voice={"file_id": "f1"}), upd(101, text="привіт")]
    monkeypatch.setattr(inbox, "api", lambda *a, **k: {"ok": True, "result": updates})

    def boom(token, file_id):
        raise subprocess.TimeoutExpired(cmd="dg_stt.sh", timeout=180)
    monkeypatch.setattr(inbox, "transcribe", boom)

    answered = inbox.poll("zirka")
    assert answered == 1
    st = json.loads((bot_env / "zirka.json").read_text())
    assert st["offset"] == 102


def test_failing_send_still_saves_state(monkeypatch, bot_env):
    """TC2: send() times out for the only update — state is still saved with the advanced
    offset and the failure lands in dropped.jsonl."""
    updates = [upd(200, text="привіт")]
    monkeypatch.setattr(inbox, "api", lambda *a, **k: {"ok": True, "result": updates})

    def boom(bot, text):
        raise subprocess.TimeoutExpired(cmd="notify.sh", timeout=300)
    monkeypatch.setattr(inbox, "send", boom)

    inbox.poll("zirka")
    st = json.loads((bot_env / "zirka.json").read_text())
    assert st["offset"] == 201
    dropped = (bot_env / "dropped.jsonl").read_text()
    assert "збій обробки" in dropped


# --- t1089: state must be persisted per update, not once after the whole batch ---------

def test_kill_mid_batch_does_not_replay_answered_messages(monkeypatch, bot_env):
    """t1089 TC1 — the oneshot service gets SIGKILLed past TimeoutStartSec mid-backlog.
    KeyboardInterrupt stands in for the kill: it escapes the loop's `except Exception`,
    so whatever is on disk at that moment is what the next run replays — and the
    already-answered first update must not be part of it."""
    updates = [upd(300, text="перше"), upd(301, text="друге")]
    monkeypatch.setattr(inbox, "api", lambda *a, **k: {"ok": True, "result": updates})
    calls = {"n": 0}

    def answer_then_die(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return "відповідь"
    monkeypatch.setattr(inbox, "answer", answer_then_die)

    with pytest.raises(KeyboardInterrupt):
        inbox.poll("zirka")
    st = json.loads((bot_env / "zirka.json").read_text())
    assert st["offset"] == 301, "the answered update must already be committed on disk"


def test_dry_run_saves_nothing_even_per_update(monkeypatch, bot_env):
    """t1089 TC2 — a dry run must not consume the queue (2026-10-30), per update either."""
    updates = [upd(400, text="привіт")]
    monkeypatch.setattr(inbox, "api", lambda *a, **k: {"ok": True, "result": updates})
    inbox.poll("zirka", dry_run=True)
    assert not (bot_env / "zirka.json").exists()
