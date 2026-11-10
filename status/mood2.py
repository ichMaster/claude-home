#!/usr/bin/env python
"""The v2 morning reading — the scaffold (t1140, phase 0 of docs/astro-v2-reference.md).

v1 (`status/mood.py`) is not replaced, moved or edited by anything here. It keeps the 08:15
slot until the owner says otherwise, and the two readings are meant to be heard side by side
on the same morning — so v2 has its own entry point, its own prompts, its own log, state and
claims, and nothing on a timer.

Three rules this file exists to enforce, before there is any content to speak of:

* **No fallback.** With no `astro2` block in the configuration the run refuses outright. A
  quiet fallback to v1's paths would let v2 append to v1's history, and that history is the
  record of three rewrites — losing it would cost more than the feature is worth.
* **One ephemeris.** The facts come from `status/astro.py`, the same module and the same call
  v1 uses. A second implementation of the sky would make the two readings incomparable, which
  is the whole point of running them in parallel.
* **No silent prompt.** A missing stage prompt names the file it looked for. An empty string
  passed to the model instead would produce a confident reading of nothing.

The prompts themselves are placeholders until phase 1 (t1143) fills them, and `--send` is
refused while they are, so a scaffold can never deliver a reading made of instructions to
itself.

    status/mood2.py                 run the pipeline for today, print it, log it
    status/mood2.py --day 2026-11-11
    status/mood2.py --dry-run       the whole pipeline, writing nothing and sending nothing
    status/mood2.py --facts         the computed facts only, no model call at all
    status/mood2.py --send          deliver it (refused while the prompts are placeholders)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "status"))
from noosconf import conf, path                                         # noqa: E402

import astro                                                            # noqa: E402
import astro_learn                                                      # noqa: E402
import mood                                                             # noqa: E402

CONFIG_KEY = "astro2"
# A prompt carrying this word is a stub, not an instruction. Phase 1 removes the marker from
# each file as it fills it, so the guard disappears by itself rather than needing a flag.
PLACEHOLDER_MARK = "ЗАГОТОВКА"


class Unconfigured(RuntimeError):
    """No `astro2` block — the one failure that must never degrade into v1's paths."""


class MissingPrompt(RuntimeError):
    """A stage has no prompt file. Named, because an empty prompt fails silently."""


class NotReady(RuntimeError):
    """Asked to send a reading the prompts cannot yet produce."""


class StageFailed(RuntimeError):
    """A stage died — timed out or returned non-zero. Named, and never a raw traceback.

    Seen on the first real run of the scaffold (2026-11-11): a placeholder prompt invited the
    model to ramble, the third stage hit the call timeout, and the entry point answered with a
    stack trace ending in `subprocess.TimeoutExpired`. A pipeline that will one day run before
    breakfast has to say which stage stopped and how long it waited.
    """


def require_config() -> dict:
    block = conf(CONFIG_KEY)
    if not isinstance(block, dict) or not block:
        raise Unconfigured(
            f"немає блоку «{CONFIG_KEY}» в конфізі — v2 не запускається. "
            "Це навмисно: без власних шляхів він писав би в історію v1.")
    return block


def conf2(key: str, default=None):
    require_config()
    return conf(f"{CONFIG_KEY}.{key}", default)


def state_path(key: str) -> Path:
    """A v2 state file. Separate from v1's by configuration, not by a suffix bolted on here."""
    require_config()
    p = path(f"{CONFIG_KEY}.{key}")
    if p is None:
        raise Unconfigured(f"у блоці «{CONFIG_KEY}» немає ключа «{key}»")
    return p


def claims_file() -> Path:
    """Where the day's claims will go. The writer arrives with phase 1 (t1143); the path is
    settled now so no stage can be tempted to borrow v1's file."""
    return state_path("claims")


def prompts_dir() -> Path:
    d = Path(str(conf2("prompts", "status/mood2")))
    return d if d.is_absolute() else HOME / d


def stages() -> list[str]:
    names = conf2("stages") or []
    if not names:
        raise Unconfigured(f"у блоці «{CONFIG_KEY}» порожній список «stages»")
    return list(names)


def prompt_text(stage: str) -> str:
    f = prompts_dir() / f"{stage}.md"
    if not f.is_file():
        raise MissingPrompt(f"немає промпта для стадії «{stage}»: {f}")
    return f.read_text(encoding="utf-8")


def placeholders() -> list[str]:
    """Which stages are still stubs. Used by the send guard and worth printing on a run."""
    return [s for s in stages() if PLACEHOLDER_MARK in prompt_text(s)]


def fill(stage: str, **values: str) -> str:
    text = prompt_text(stage)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value or "")
    return text


def fact_text(day: date) -> str:
    """The day's facts, rendered exactly as v1 renders them — one ephemeris, one formatter."""
    return mood.fact_lines(astro.facts(day))


def reference_text(day: date) -> str:
    """His calendar for that date, or an honest note that there is none.

    Phase 1 reads this as the source of the reading; the scaffold only has to prove it
    reaches the stage prompts.
    """
    text = astro_learn.for_day(day)
    return text.strip() if text else "(календаря на цей день немає)"


def call(stage: str, prompt: str) -> str:
    models = conf2("models") or {}
    seconds = int(conf2("timeout", mood.CALL_TIMEOUT))
    try:
        return mood.run_claude(prompt, models.get(stage, ""), timeout=seconds)
    except subprocess.TimeoutExpired:
        raise StageFailed(f"стадія «{stage}» не відповіла за {seconds} с") from None
    except RuntimeError as e:
        raise StageFailed(f"стадія «{stage}» не вдалася: {e}") from None


def run(day: date, dry_run: bool = False, note=lambda *a: None) -> dict:
    """Every stage in order, each seeing the previous one's answer. Returns stage → text."""
    require_config()
    facts, reference = fact_text(day), reference_text(day)
    out: dict[str, str] = {}
    previous = ""
    for stage in stages():
        note(f"стадія {stage}")
        answer = call(stage, fill(
            stage,
            ДАТА=day.isoformat(),
            ФАКТИ=facts,
            ЕТАЛОН=reference,
            ПОПЕРЕДНЄ=previous,
            БЮДЖЕТ=str(conf2("budget_chars", 1200)),
            МАКСИМУМ=str(conf2("items_max", 5)),
            ГОЛОСНЕ=str(conf2("loud_min", 3)),
        ))
        out[stage] = answer
        previous = answer
    if not dry_run:
        log_run(day, out)
        save_state(day, out)
    return out


def log_run(day: date, parts: dict[str, str]) -> None:
    """Append the whole run, like v1's log — a correction is a new block, never an edit."""
    f = state_path("log")
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n===== {day.isoformat()} =====\n")
        for name, body in parts.items():
            fh.write(f"\n--- {name} ---\n{(body or '').strip()}\n")


def save_state(day: date, parts: dict[str, str]) -> None:
    """What a probe or the panel would show without paying for the reading again."""
    f = state_path("state")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(
        {"day": day.isoformat(),
         "stages": parts,
         "reading": parts.get(stages()[-1], ""),
         "placeholders": placeholders(),
         "saved_at": datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=2), encoding="utf-8")


def send(text: str) -> None:
    """Deliver through v1's sender — same bot, same voice profile, so the two are comparable.

    Refused while any stage prompt is a stub: a reading built from placeholder instructions
    would be indistinguishable, to the ear, from a real one.
    """
    stubs = placeholders()
    if stubs:
        raise NotReady("ще заготовки, не промпти: " + ", ".join(stubs)
                       + " — заповнюються у фазі 1 (t1143)")
    mood.send(text, role="mood")


def main() -> int:
    ap = argparse.ArgumentParser(description="ранкове читання v2 (каркас, фаза 0)")
    ap.add_argument("--day", help="дата YYYY-MM-DD (типово — сьогодні)")
    ap.add_argument("--dry-run", action="store_true", help="усе показати, нічого не писати")
    ap.add_argument("--facts", action="store_true", help="лише обчислені факти, без моделі")
    ap.add_argument("--send", action="store_true", help="надіслати (поки відмовляє)")
    args = ap.parse_args()

    day = date.fromisoformat(args.day) if args.day else mood.today()
    try:
        require_config()
        if args.facts:
            print(fact_text(day))
            return 0
        parts = run(day, dry_run=args.dry_run, note=lambda m: print(m, file=sys.stderr))
        reading = parts.get(stages()[-1], "")
        print(reading)
        if args.send:
            send(reading)
        stubs = placeholders()
        if stubs:
            print(f"\n(заготовки: {', '.join(stubs)} — фаза 1, t1143)", file=sys.stderr)
    except (Unconfigured, MissingPrompt, NotReady) as e:
        print(f"v2: {e}", file=sys.stderr)
        return 2
    except StageFailed as e:
        print(f"v2: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
