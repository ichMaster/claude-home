#!/usr/bin/env python3
"""One line per outgoing message — the record of what this system actually said.

    printf '%s' "$text" | sent_log.py --bot main --kind digest-headless.sh \
        --text-code 200 --voice-code 200

Called by `notify.sh` after it has sent, so the codes are Telegram's answer rather than an
assumption: a message that failed is the whole reason to keep this (t1119). Nothing else in
the project knew what had been said — the digest, the forecast, the reminders and every reply
went out and were gone, and in `systemctl` a timer that ran and stayed silent looks exactly
like one that did its job.

The chat id is deliberately not stored: the bot's name says where the message went, and the
id is personal and already lives in one file.

Never raises: a log is a record, not a gate. A message must not fail to be sent because the
note about it could not be written.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import atomic_write_text, conf, locked, path              # noqa: E402

LOG = path("sent.log", "status/state/chat-log.jsonl")
MAX_TEXT = 4000


def max_lines() -> int:
    """A record, not an archive: this machine has one disk at 91 % full."""
    return int(conf("sent.max_lines", 5000))


def caller() -> str:
    """The name of the script that called `notify.sh`, as the kind of message.

    Enough for a caller that is a script — a reminder says `remind.py`. It cannot work where
    the caller is a model: the four units that send through `claude -p` have a harness shell
    as the parent, and those export `NOOS_SENT_KIND` instead (t1121).
    """
    try:
        ppid = os.getppid()
        parent = subprocess.run(["ps", "-o", "ppid=,args=", "-p", str(ppid)],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        grandparent = parent.split()[0] if parent else ""
        if grandparent:
            args = subprocess.run(["ps", "-o", "args=", "-p", grandparent],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
            for word in args.split():
                if _throwaway(word):
                    continue
                name = Path(word).name
                if name.endswith((".py", ".sh")) and name != "notify.sh":
                    return name
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        pass
    return ""


def _throwaway(word: str) -> bool:
    """A wrapper script in /tmp is not the kind of a message. The terminal harness runs
    commands through a generated `snapshot-bash-*.sh`, and recording that as the sender
    would be noise where a name is expected (t1119)."""
    name = Path(word).name
    return word.startswith(("/tmp/", "/var/tmp/")) or name.startswith(("snapshot-", "bash-"))


def append(bot: str, kind: str, text: str, codes: dict, voice: bool,
           asked: str = "", error: str = "") -> None:
    """Append one record and trim the file to the newest `max_lines`. Never raises.

    The append and the trim are one locked section: the trim is a read-modify-write, and
    several timers fire at once here — the watcher every 15 minutes, the bots every two,
    the reminders every five — which lost 11 to 15 of 20 concurrent records (t1121).
    """
    try:
        wanted = [int(v) for v in codes.values() if str(v).strip()]
        rec = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "bot": bot or "main",
            "kind": kind or caller(),
            "ok": bool(wanted) and all(c == 200 for c in wanted),
            "codes": {k: int(v) for k, v in codes.items() if str(v).strip()},
            "voice": bool(voice),
            "chars": len(text or ""),
            "text": (text or "")[:MAX_TEXT],
        }
        if asked and asked != rec["bot"]:
            # the message fell back to the main bot: say both, because this record is the
            # only witness to where it went (t1121)
            rec["asked"] = asked
        if error:
            rec["error"] = error[:200]
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if not LOG.exists():
            # This file holds the text of every message sent — the most personal thing in
            # status/state, so it is created 600 rather than inheriting the umask (t1121).
            os.close(os.open(LOG, os.O_CREAT | os.O_WRONLY, 0o600))
        line = json.dumps(rec, ensure_ascii=False)
        with locked(LOG):
            with LOG.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            cap = max_lines()
            lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > cap:
                atomic_write_text(LOG, "\n".join(lines[-cap:]) + "\n")
    except Exception:                                                   # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="записати відправлене повідомлення")
    ap.add_argument("--bot", default="main")
    ap.add_argument("--kind", default="")
    ap.add_argument("--text-code", default="")
    ap.add_argument("--voice-code", default="")
    ap.add_argument("--asked", default="", help="the bot that was asked for, if it differs")
    ap.add_argument("--error", default="", help="why a part never reached Telegram")
    args = ap.parse_args()
    codes = {}
    if str(args.text_code).strip():
        codes["text"] = args.text_code
    if str(args.voice_code).strip():
        codes["voice"] = args.voice_code
    append(bot=args.bot, kind=args.kind, text=sys.stdin.read(), codes=codes,
           voice="voice" in codes, asked=args.asked, error=args.error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
