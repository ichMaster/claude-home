"""t1164 + t1165 — the handoff note must come from the conversation, and a note that
failed must neither wipe the context nor be reported with a stale size.

Every headless `claude -p` run writes its transcript into the same project directory as the
main session, so "newest file" is not "the conversation" (t1164). And restart-session.sh used
to ignore handoff.py's exit code, touch `.fresh` anyway, and report the size of
`handoff-last.md` — a previous restart's note (t1165)."""
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# loaded by path, not by sys.path: memory/ also holds search.py, which would shadow
# status/bots/search.py for every test collected after this one
_spec = importlib.util.spec_from_file_location("noos_handoff", ROOT / "memory" / "handoff.py")
handoff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(handoff)


def _transcript(f: Path, user_texts, mtime):
    recs = []
    for t in user_texts:
        recs.append({"message": {"role": "user", "content": t}})
        recs.append({"message": {"role": "assistant",
                                 "content": [{"type": "text", "text": f"відповідь на {t}"}]}})
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs),
                 encoding="utf-8")
    os.utime(f, (mtime, mtime))


def test_newer_headless_transcript_is_skipped(tmp_path):
    """TC1 (t1164): the digest ran after the owner's last word — its one-prompt transcript
    is newer, but the note must still come from the conversation."""
    now = time.time()
    talk = tmp_path / "talk.jsonl"
    _transcript(talk, ["привіт", "що з задачами?", "перенеси блок", "дякую"], now - 3600)
    probe = tmp_path / "probe.jsonl"
    _transcript(probe, ["Збери дайджест і надішли його."], now)
    chosen, turns = handoff.pick_transcript([probe, talk])
    assert chosen == talk, "записка складається з хвоста головної розмови, не з проби"
    assert any("перенеси блок" in t for t in turns)


def test_fallback_when_nothing_qualifies(tmp_path):
    """TC2 (t1164): only headless transcripts exist → the newest still gives a note."""
    now = time.time()
    a = tmp_path / "a.jsonl"
    _transcript(a, ["одна репліка"], now - 60)
    b = tmp_path / "b.jsonl"
    _transcript(b, ["інша репліка"], now)
    chosen, turns = handoff.pick_transcript([a, b])
    assert chosen == b
    assert turns


# --- t1165: restart-session.sh against stub binaries ----------------------------------------

def _run_restart(tmp_path, handoff_ok: bool):
    home = tmp_path
    ch = home / "claude-home"
    (ch / "memory").mkdir(parents=True)
    vbin = ch / ".venv-voice" / "bin"
    stub = home / "stub-bin"
    for d in (vbin, stub):
        d.mkdir(parents=True)

    # a previous restart's note — the stale file the old report used to measure
    (ch / "memory" / "handoff-last.md").write_text("стара записка на багато символів\n" * 9)

    log = home / "notify.log"
    (ch / "notify.sh").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n')
    if handoff_ok:
        (vbin / "python").write_text(
            f'#!/bin/sh\nprintf "note" > "{ch}/memory/handoff.md"\nexit 0\n')
    else:
        (vbin / "python").write_text('#!/bin/sh\nexit 1\n')
    for name in ("systemctl", "sleep"):
        (stub / name).write_text('#!/bin/sh\nexit 0\n')
    (stub / "pgrep").write_text('#!/bin/sh\nexit 0\n')
    for f in list(stub.iterdir()) + [ch / "notify.sh", vbin / "python"]:
        f.chmod(0o755)

    subprocess.run(["bash", str(ROOT / "restart-session.sh"), "--summary"],
                   check=False, timeout=30, capture_output=True, text=True,
                   env={"HOME": str(home), "USER": os.environ.get("USER", "x"),
                        "PATH": f"{stub}:/usr/bin:/bin"})
    return ch, log.read_text(encoding="utf-8") if log.exists() else ""


def test_failed_handoff_keeps_context_and_says_so(tmp_path):
    """TC1 (t1165): handoff.py failed → no .fresh (the thread survives as --continue), and
    the report says the note failed instead of quoting the stale handoff-last.md size."""
    ch, notified = _run_restart(tmp_path, handoff_ok=False)
    assert not (ch / ".fresh").exists(), "контекст стерто без записки — нитка втрачена"
    assert "не склалась" in notified
    assert "Записка: " not in notified, "розмір узято зі старої handoff-last.md"


def test_successful_handoff_reports_fresh_size(tmp_path):
    """TC2 (t1165): the note was written → .fresh is set and its own size is reported."""
    ch, notified = _run_restart(tmp_path, handoff_ok=True)
    assert (ch / ".fresh").exists()
    assert "Записка: 4 символів" in notified
