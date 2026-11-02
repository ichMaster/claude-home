"""The horoscope pipeline, read from its own log — collectors for screen 4.

`status/state/mood.log` is append-only and already past 1700 lines. Everything the forecast
does is in there; nothing about it is browsable. These functions turn it into rows, and
stay pure over text passed in so the tests never touch the real log.

Writes are not here. The screen's route runs the existing scripts — `astro_learn.py`,
`mood_feedback.py`, `mood.py` — so validation stays in one place and the panel keeps having
no store of its own.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path                                         # noqa: E402

HOME = Path(__file__).resolve().parents[1]
PARKED = HOME / "status" / "state" / "astro-reference-inbox"

DAY_HEAD = re.compile(r"(?m)^===== (\d{4}-\d{2}-\d{2}) =====[ \t]*$")
STAGE_HEAD = re.compile(r"(?m)^--- (.+?) ---$")
# the legacy five-block shape, with the budget each block was held to (pre-t1126 days)
BUDGETS = {"КОРОТКО": 300, "ПІДСУМОК": 400, "ІСТОРІЯ": 1800,
           "ГОЛОВНЕ": 450, "НАСАМКІНЕЦЬ": 300}
# the current shape (t1126): no per-block budget — astro.budget_chars binds the spoken
# total, and ОСНОВА is text-only, outside it
NEW_BLOCKS = ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА", "ОСНОВА")
SPOKEN_BLOCKS = ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА")
# the stage that holds the reading as it was sent, newest name first (mirrors
# mood._FINAL_SECTIONS; перевірка holds the raw check output, never the reading)
SUMMARY_STAGES = ("письмо (перероблено)", "письмо",
                  "підсумок (перероблено)", "підсумок", "прогноз")
BLOCK_HEAD = re.compile(r"(?m)^[\s*#_>•·—-]*("
                        + "|".join(list(BUDGETS) + list(NEW_BLOCKS))
                        + r")[\s*_#]*:?[ \t]*")


def reading_blocks(summary: str) -> list[dict]:
    """The reading split into its blocks, each measured.

    A new-format reading (t1126) is measured as ДЕНЬ/ПРОГНОЗ/ДІЯ/ДУГА/ОСНОВА with the
    spoken total held to `astro.budget_chars`; a legacy one keeps its per-block budgets.
    A block the reading does not contain is returned as missing rather than omitted: a
    quietly short page would hide that.
    """
    marks = list(BLOCK_HEAD.finditer(summary or ""))
    found: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(summary)
        found[m.group(1).upper()] = summary[m.end():end].strip()
    out = []
    if any(name in found for name in NEW_BLOCKS):
        for name in NEW_BLOCKS:
            text = found.get(name, "")
            out.append({"name": name, "text": text, "chars": len(text), "budget": None,
                        "over": False, "missing": not text})
        budget = int(conf("astro.budget_chars", 1200))
        spoken = sum(len(found.get(name, "")) for name in SPOKEN_BLOCKS)
        out.append({"name": "РАЗОМ (голос)", "text": "", "chars": spoken, "budget": budget,
                    "over": spoken > budget, "missing": False, "total": True})
        return out
    for name, budget in BUDGETS.items():
        text = found.get(name, "")
        out.append({"name": name, "text": text, "chars": len(text), "budget": budget,
                    "over": len(text) > budget, "missing": not text})
    return out


def day_runs(log: str, day: date | str) -> list[dict]:
    """Every logged run for one date, newest first, each with its stages in order.

    A day can hold several blocks — the morning run, a `--resume`, a recomputation after a
    reference — and "which run produced this" is the question the screen exists to answer,
    so they are never merged.
    """
    want = day if isinstance(day, str) else day.isoformat()
    marks = list(DAY_HEAD.finditer(log or ""))
    runs = []
    for i, m in enumerate(marks):
        if m.group(1) != want:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(log)
        block = log[m.end():end]
        stages = []
        heads = list(STAGE_HEAD.finditer(block))
        for j, h in enumerate(heads):
            stop = heads[j + 1].start() if j + 1 < len(heads) else len(block)
            stages.append({"name": h.group(1), "text": block[h.end():stop].strip()})
        runs.append({"day": want, "stages": stages,
                     "summary": next((s["text"] for s in reversed(stages)
                                      if s["name"] in SUMMARY_STAGES), "")})
    return list(reversed(runs))


def parked(folder: Path | None = None) -> list[dict]:
    """References stored by Zirka's chat and not yet ingested (t1059), newest first."""
    d = folder or PARKED
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.txt"), reverse=True):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # name is <stamp>-<day>.txt
        day = f.stem.split("-", 2)[2] if f.stem.count("-") >= 2 else ""
        out.append({"file": str(f), "name": f.name, "day": day,
                    "chars": len(text), "head": text[:400]})
    return out


def references(limit: int = 10) -> list[dict]:
    """What is already in the reference store, newest first."""
    f = Path(str(path("astro.reference", "status/state/astro-reference.jsonl")))
    if not f.is_file():
        return []
    rows = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))[:limit]


def feedback(limit: int = 12) -> list[dict]:
    f = Path(str(path("astro.feedback", "status/state/mood-feedback.jsonl")))
    if not f.is_file():
        return []
    rows = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))[:limit]


def rules_text() -> tuple[str, str]:
    """(rules from his own days, rules from the astrologer's readings) — labelled apart,
    because one says whether we read him right and the other says how to read."""
    own = Path(str(path("astro.calibration", "status/state/mood-calibration.md")))
    ref = Path(str(path("astro.reference_rules", "status/state/astro-reference-rules.md")))
    return (own.read_text(encoding="utf-8", errors="replace") if own.is_file() else "",
            ref.read_text(encoding="utf-8", errors="replace") if ref.is_file() else "")


def log_text() -> str:
    f = Path(str(path("astro.log", "status/state/mood.log")))
    return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""


def today() -> date:
    return datetime.now().astimezone().date()
