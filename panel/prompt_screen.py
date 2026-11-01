"""The system prompt and the scenario prompts — collectors for screens 2 and 3.

Screen 2 is the one that justified the panel: **showing the assistant to itself.** The
prompt the session wakes up with is assembled by `start.sh` out of `persona.md`, the pinned
facts and — once — the handoff note, and then it is invisible to everything, including the
session. This module rebuilds it in the same order and says how big each part is.

It also answers the question the files themselves cannot: an edit to `persona.md` or
`CLAUDE.md` is read at launch, so a change means nothing until a restart. Comparing each
file's mtime with the session's own start time is enough to say which is which, and needs
nothing recorded anywhere.

Screen 3 is the prompts that belong to no channel — the digest, the forecast's nine stages,
the bots, the nightly review. Reading or re-running one meant a terminal.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf                                              # noqa: E402

HOME = Path(__file__).resolve().parents[1]
# Characters per token, roughly, for Ukrainian prose in this tokenizer's neighbourhood. It is
# an estimate and the screen says so: the point is the order of magnitude against a context
# window, not a number anyone should budget against.
CHARS_PER_TOKEN = 3.5


def assembled(persona: str, facts: str, handoff: str | None,
              permissions: str | None = None) -> dict:
    """The prompt in the exact order `start.sh` concatenates it.

    The handoff note is part of it only while `memory/handoff.md` exists: `start.sh` moves
    the file to `handoff-last.md` as it reads it, so a consumed note is history and showing
    it as part of the live prompt would be a lie.
    """
    parts = [{"name": "persona.md", "text": persona or ""},
             {"name": "факти", "text": facts or ""}]
    if permissions:
        parts.append({"name": "дозволи", "text": permissions})
    if handoff:
        parts.append({"name": "естафета", "text": handoff})
    text = "\n".join(p["text"] for p in parts if p["text"])
    for p in parts:
        p["chars"] = len(p["text"])
    return {"parts": parts, "text": text, "chars": len(text),
            "tokens": int(len(text) / CHARS_PER_TOKEN)}


def stale_files(started: float, paths: list[Path]) -> list[dict]:
    """Which of these files changed after the session started — i.e. is saved but not in
    force. A file that cannot be read is left out: unknown is not stale."""
    out = []
    for p in paths:
        try:
            mtime = Path(p).stat().st_mtime
        except OSError:
            continue
        if mtime > started:
            ago = max(0, int((datetime.now().timestamp() - mtime) // 60))
            out.append({"file": Path(p).name,
                        "when": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                        "ago": f"{ago} хв" if ago < 90 else f"{ago // 60} год"})
    return out


def prompt_files(paths: list[Path], dirty: set[str] | None = None) -> list[dict]:
    """`persona.md` and `CLAUDE.md`: their size and whether they differ from the commit."""
    rows = []
    for p in paths:
        p = Path(p)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            rows.append({"file": p.name, "chars": 0, "dirty": False, "text": "",
                         "exists": False})
            continue
        rows.append({"file": p.name, "chars": len(text), "text": text, "exists": True,
                     "dirty": p.name in (dirty or set())})
    return rows


def scenarios() -> list[dict]:
    return list(conf("panel.scenarios", []) or [])


def scenario_rows(items: list[dict], timers: dict[str, dict],
                  home: Path | None = None) -> list[dict]:
    """One row per scenario: its prompts with their sizes, the timer that fires it, and the
    commands. A prompt file that is missing is named as missing — a scenario quietly short
    of a prompt it needs is exactly the kind of thing this screen exists to show."""
    base = Path(home or HOME)
    rows = []
    for item in items or []:
        timer = timers.get(str(item.get("unit") or ""), {})
        prompts = []
        for name in item.get("prompts") or []:
            f = base / str(name)
            try:
                prompts.append({"file": str(name), "exists": True,
                                "chars": len(f.read_text(encoding="utf-8"))})
            except OSError:
                prompts.append({"file": str(name), "exists": False, "chars": 0})
        rows.append({
            "name": str(item.get("name") or "?"),
            "what": str(item.get("what") or ""),
            "unit": str(item.get("unit") or ""),
            "schedules": timer.get("schedules") or [],
            "last": timer.get("last") or "",
            "failed": bool(timer.get("failed")),
            "cmd": " ".join(str(x) for x in (item.get("cmd") or [])),
            "dry": " ".join(str(x) for x in (item.get("dry") or [])),
            "detach": bool(item.get("detach")),
            "prompts": prompts,
        })
    return rows


def by_name(name: str) -> dict | None:
    """A scenario by name, or nothing. The name arrives from a form, so it is never used
    for anything but this lookup — the command comes from the config, not from the request."""
    for item in scenarios():
        if str(item.get("name")) == name:
            return item
    return None
