"""What was actually said — collectors for screen 11.

`status/state/chat-log.jsonl` is written by `notify.sh` through
`status/tools/sent_log.py`: one line per outgoing message, with Telegram's own answer. This
module reads it and nothing else.

**Metadata, not bodies, by default.** The text of a digest is the owner's calendar and his
mail, so `panel.sent_bodies` decides whether the body is rendered at all — the same lesson as
t1094, where the journal pane published the same material.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path                                        # noqa: E402

LOG = path("sent.log", "status/state/chat-log.jsonl")


def rows(log: Path | None = None, bot: str = "", kind: str = "",
         limit: int | None = None) -> list[dict]:
    """The messages, newest first, optionally narrowed by bot and kind.

    A torn last line is expected — the file is appended to while this reads it — and is
    skipped rather than fatal.
    """
    f = Path(log or LOG)
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if bot and str(rec.get("bot") or "") != bot:
            continue
        if kind and str(rec.get("kind") or "") != kind:
            continue
        out.append(rec)
        if limit and len(out) >= limit:
            break
    return out


def counters(items: list[dict]) -> dict:
    """What the top of the screen says: how many, how many spoken, how many failed."""
    return {
        "total": len(items),
        "voice": sum(1 for r in items if r.get("voice")),
        "failed": sum(1 for r in items if not r.get("ok", True)),
    }


def bots(items: list[dict]) -> list[str]:
    return sorted({str(r.get("bot") or "main") for r in items})


def kinds(items: list[dict]) -> list[str]:
    return sorted({str(r.get("kind") or "") for r in items if r.get("kind")})


def bodies_shown() -> bool:
    return bool(conf("panel.sent_bodies", False))
