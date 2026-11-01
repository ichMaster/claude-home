"""The panel's own line in the change log.

`docs/features/ADMIN-PANEL.md` states it as the panel's one hard rule — "every write appends
to `changelog/` through the same hook path the assistant uses" — and the Rules screen renders
it as a standing rule. It was not true: the hook is a Claude Code `PostToolUse` hook, so it
sees the session's tool calls and nothing the panel does on its own (t1113). A panel edit left
no trace anywhere, which is the opposite of the consequence the doc spells out: "a week later
it is still visible who changed what".

The record has the same six fields the hook writes, so one reader serves both and the Changes
screen needs no special case. `session` is `panel`, because that is the honest answer to who
did it — and the log is append-only by design and by `chattr +a`, so this module only ever
appends.

A failure here is swallowed: the log is a record, not a gate. An unwritable log must never
cost the edit it was recording.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import path                                              # noqa: E402

LOG_DIR = path("changelog.dir")
MAX_DETAIL = 400


def record(kind: str, target: str, detail: str = "") -> None:
    """Append one line. Never raises."""
    try:
        folder = Path(LOG_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        home = os.path.expanduser("~")
        shown = str(target)
        if shown.startswith(home):
            shown = "~" + shown[len(home):]
        rec = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "kind": str(kind),
            "target": shown,
            "detail": str(detail)[:MAX_DETAIL],
            "session": "panel",
            "cwd": str(Path(__file__).resolve().parents[1]),
        }
        day = datetime.now().strftime("%Y-%m-%d")
        with (folder / f"{day}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:                                                   # noqa: BLE001
        pass
