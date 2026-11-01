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
from noosconf import atomic_write_text, conf, locked, version_failed   # noqa: E402

HOME = Path(__file__).resolve().parents[1]
# The only two files this screen may write, by name. A path from a form never becomes a
# target (t1103) — and these two are the ones the owner asked to edit in the panel.
EDITABLE = {"persona.md", "CLAUDE.md"}
# Characters per token, roughly, for Ukrainian prose in this tokenizer's neighbourhood. It is
# an estimate and the screen says so: the point is the order of magnitude against a context
# window, not a number anyone should budget against.
CHARS_PER_TOKEN = 3.5


HANDOFF_HEAD = "## Естафета з попередньої сесії"


def assembled(persona: str, facts: str, handoff: str | None,
              permissions: str | None = None) -> dict:
    """The prompt in the exact order and shape `start.sh` concatenates it.

    The handoff note **is** part of the live prompt when the running session consumed one —
    `start.sh` moves `handoff.md` to `handoff-last.md` as it reads it, so the file being gone
    is the proof the session carries the note, not the proof it does not. Reading it the
    other way understated this session's prompt by 36 % and left out the whole thread of
    yesterday (t1111). `handoff_state()` decides which case this is; the heading below is
    what the shell writes before the note, and without it the block is not what the session
    sees.
    """
    # Command substitution strips trailing newlines, so each part is stripped the same way
    # the shell strips it — otherwise the total is a couple of characters off the real one,
    # and this screen's whole claim is that its arithmetic is the shell's (t1111).
    parts = [{"name": "persona.md", "text": (persona or "").rstrip("\n")},
             {"name": "факти", "text": (facts or "").rstrip("\n")}]
    if permissions:
        parts.append({"name": "дозволи", "text": permissions.rstrip("\n")})
    text = "\n".join(p["text"] for p in parts if p["text"])
    if handoff:
        note = handoff.rstrip("\n")
        parts.append({"name": "естафета", "text": note})
        text += f"\n\n{HANDOFF_HEAD}\n{note}"
    for p in parts:
        p["chars"] = len(p["text"])
    return {"parts": parts, "text": text, "chars": len(text),
            "tokens": int(len(text) / CHARS_PER_TOKEN)}


def handoff_state(folder: Path | None = None, started: float = 0.0,
                  now: float | None = None) -> dict:
    """Which handoff note the running session actually has.

    Four answers, and the difference matters because the screen claims to show what the
    session sees: `pending` — `handoff.md` is still on disk, so the *next* start will take
    it; `consumed` — it was archived before this session came up, i.e. this session has it;
    `unknown` — the archive is newer than this session's start, so it belongs to a session
    that has not started yet, and claiming it would be worse than silence; `none`.
    """
    import time
    base = Path(folder or (HOME / "memory"))
    now = time.time() if now is None else now
    pending = base / "handoff.md"
    archived = base / "handoff-last.md"
    try:
        if pending.is_file():
            return {"state": "pending", "text": pending.read_text(encoding="utf-8"),
                    "when": pending.stat().st_mtime}
    except OSError:
        pass
    try:
        when = archived.stat().st_mtime
        if started and when > started:
            return {"state": "unknown", "text": "", "when": when}
        return {"state": "consumed", "text": archived.read_text(encoding="utf-8"),
                "when": when}
    except OSError:
        return {"state": "none", "text": "", "when": 0.0}


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


def save_file(name: str, text: str, confirm: bool = False) -> tuple[bool, str]:
    """Write one of the two editable files. Returns (written, what to say).

    Every refusal here answers a way this could destroy the file rather than change it:
    a name that is not on the list, an empty save, or a save that shrinks the file so much
    that a truncated paste is the likelier explanation than an edit. The write itself goes
    through the versioned atomic path, so even an approved mistake is one
    `tools/versions.py restore` away.
    """
    if name not in EDITABLE:
        return False, f"Тут редагуються лише {', '.join(sorted(EDITABLE))}."
    # A browser normalises a textarea's newlines to CRLF, so one save rewrote every line of
    # the file — and the diff the commit-time security review has to read became the whole
    # file (t1112).
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not (text or "").strip():
        return False, "Порожній файл — не зберігаю. Це майже завжди не те, чого хотіли."
    target = Path(HOME) / name
    try:
        before = target.read_text(encoding="utf-8")
    except OSError:
        return False, f"{name} не прочитався, тож і не перезаписую."
    ratio = float(conf("panel.edit_min_ratio", 0.5))
    if before and len(text) < len(before) * ratio and not confirm:
        return False, (f"{name} скоротився б із {len(before)} до {len(text)} знаків — "
                       "це схоже на обрізану вставку. Натисни ще раз, щоб підтвердити.")
    try:
        # under the file's lock, so a double-click cannot interleave two bodies (t1104)
        with locked(target):
            atomic_write_text(target, text)
    except OSError as exc:
        return False, f"Не записалось: {exc}"
    warn = ("" if not version_failed(target) else
            " УВАГА: копію попереднього вмісту зберегти не вдалось.")
    return True, (f"{name} збережено ({len(text)} знаків). Діє після перезапуску сесії — "
                  "банер вище про це й скаже." + warn)
