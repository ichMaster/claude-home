#!/usr/bin/env python
"""Calibration of the morning forecast against how the day actually felt.

The owner's point (2026-10-27): «я це відчуваю по іншому ніж ти подаєш». A forecast nobody
checks is decoration. So the day's own verdict is collected, compared with what was
promised, and the difference is turned into rules the next forecast has to obey.

Three parts:

1. **Collection.** Whatever he says about how a day went is appended to
   `status/state/mood-feedback.jsonl` — append-only, one line per remark, with the day it
   is about. He speaks rather than types, so this is usually the session writing down a
   transcribed voice message; `/feel <text>` and `ask` (an evening question on a timer) are
   the other two ways in.
2. **Comparison.** `calibrate` takes one day's forecast out of the mood log, puts it next to
   that day's remarks, and asks for three things: where the reading matched, where it
   missed, and **one concrete rule** that would have made it right. The rule is what
   matters; "be more careful" is not a rule.
3. **Feeding back.** `rules` returns the accumulated rules, newest first, and
   `status/mood.py` injects them into the weighing, the draft and the summary. So a miss
   changes the next reading rather than being noted and forgotten.

The rules file (`status/state/mood-calibration.md`) is append-only like the rest: a rule
that turns out wrong is superseded by a new line, never edited away.

    mood_feedback.py add "текст" [--day YYYY-MM-DD]
    mood_feedback.py list [--day YYYY-MM-DD]
    mood_feedback.py ask                 send the evening question (voice + text)
    mood_feedback.py calibrate [--day]   compare that day and append the rules
    mood_feedback.py rules [--limit 8]   the rules, as the prompts see them
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path  # noqa: E402

HOME = Path(__file__).resolve().parents[1]
PROMPTS = HOME / "status" / "mood"


def today() -> date:
    return datetime.now(ZoneInfo(conf("astro.tz", "Europe/Kyiv"))).date()


def feedback_file() -> Path:
    return path("astro.feedback", "status/state/mood-feedback.jsonl")


def rules_file() -> Path:
    return path("astro.calibration", "status/state/mood-calibration.md")


# --- collection ----------------------------------------------------------------------------------------------------

def add(text: str, day: date, source: str = "telegram") -> None:
    """Append one remark. The day defaults to today, but an evening remark about the morning
    is still about today, so the caller may say otherwise."""
    f = feedback_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                             "day": day.isoformat(), "text": text.strip(), "source": source},
                            ensure_ascii=False) + "\n")


def remarks(day: date | None = None) -> list[dict]:
    f = feedback_file()
    if not f.is_file():
        return []
    rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [r for r in rows if day is None or r.get("day") == day.isoformat()]


# --- comparison ----------------------------------------------------------------------------------------------------

def forecast_of(day: date) -> str:
    """That day's forecast as it was sent, out of the append-only mood log."""
    sys.path.insert(0, str(HOME / "status"))
    import mood  # noqa: E402  — the log parser lives there

    parts = mood.logged_sections(day)
    return parts.get("підсумок (перероблено)") or parts.get("підсумок") or parts.get("прогноз") or ""


def calibrate(day: date, note=print) -> str:
    """Compare one day's forecast with the day's remarks and append the rules that follow.

    Returns the model's answer, or an empty string when there is nothing to compare: no
    remarks means no evidence, and inventing a correction from silence is worse than none.
    """
    said = remarks(day)
    if not said:
        note(f"немає фідбеку за {day.isoformat()}")
        return ""
    given = forecast_of(day)
    if not given:
        note(f"немає прогнозу за {day.isoformat()}")
        return ""

    sys.path.insert(0, str(HOME / "status"))
    import mood  # noqa: E402

    prompt = (PROMPTS / "calibrate.md").read_text(encoding="utf-8")
    prompt = (prompt.replace("{{ДАТА}}", day.isoformat())
                    .replace("{{ПРОГНОЗ}}", given)
                    .replace("{{ФІДБЕК}}", "\n".join(f"- [{r['ts'][11:16]}] {r['text']}" for r in said))
                    .replace("{{ПРАВИЛА}}", rules(limit=12) or "правил поки немає"))
    answer = mood.run_claude(prompt, conf("astro.models.judge", ""))

    f = rules_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n## {day.isoformat()}\n{answer.strip()}\n")
    return answer


def rules(limit: int = 8) -> str:
    """The accumulated rules, newest first — this is what the prompts receive.

    Only the `ПРАВИЛО:` lines are passed on: the match/miss discussion is history, the rule
    is the part that has to change the next reading.
    """
    f = rules_file()
    if not f.is_file():
        return ""
    found: list[str] = []
    for line in reversed(f.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip().lstrip("-*• ").strip()
        if stripped.upper().startswith("ПРАВИЛО"):
            body = stripped.split(":", 1)[-1].strip()
            if body and body not in found:
                found.append(body)
        if len(found) >= limit:
            break
    return "\n".join(f"- {r}" for r in found)


# --- the evening question ------------------------------------------------------------------------------------------

QUESTION = ("Як день насправді пройшов? Скажи своїми словами — що збіглося з ранковим "
            "прогнозом, а що ні. Коротко, двома реченнями, цього досить.")


def question_for(day: date) -> str:
    """The evening question, built from that morning's own claims.

    A generic "how was your day" gets a generic answer. The owner asked for the diary
    version — «чи відчувалось це або це?» — so one cheap call turns two or three of the
    day's specific promises into questions that can be answered yes or no. Without a
    forecast to quote, the generic question stands.
    """
    given = forecast_of(day)
    if not given:
        return QUESTION
    sys.path.insert(0, str(HOME / "status"))
    import mood  # noqa: E402

    prompt = ((PROMPTS / "ask.md").read_text(encoding="utf-8")
              .replace("{{ДАТА}}", day.isoformat()).replace("{{ПРОГНОЗ}}", given))
    try:
        return mood.plain(mood.run_claude(prompt, conf("astro.models.layer", "sonnet"),
                                          mood.FACT_TIMEOUT)) or QUESTION
    except Exception:
        return QUESTION


def answered_tonight(day: date) -> bool:
    """Has he already said something about this day late enough to count as the evening's
    answer? Remarks before `astro.ask_after_hour` are about the morning, not the day."""
    cutoff = int(conf("astro.ask_after_hour", 18))
    for r in remarks(day):
        try:
            if int(r["ts"][11:13]) >= cutoff:
                return True
        except (KeyError, ValueError):
            continue
    return False


def ask(day: date | None = None, force: bool = False) -> None:
    """Ask once in the evening, in the forecast's own voice, so the question is recognisable."""
    day = day or today()
    if not force and answered_tonight(day):
        return                                    # he got there first; no need to prod
    cmd = [str(HOME / "notify.sh")]
    if conf("telegram.bots.mood"):
        cmd += ["--bot", "mood"]                  # the question belongs in the forecast's chat
    if conf("voice.roles.mood"):
        cmd += ["--voice-profile", "mood"]
    cmd.append(f"🜛 {question_for(day)}")
    subprocess.run(cmd, check=False, cwd=str(HOME), timeout=300)


def main() -> int:
    ap = argparse.ArgumentParser(description="калібрування прогнозу за фактом дня")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="записати фідбек")
    p_add.add_argument("text")
    p_add.add_argument("--day")
    p_add.add_argument("--source", default="telegram")

    p_list = sub.add_parser("list", help="показати фідбек")
    p_list.add_argument("--day")

    p_ask = sub.add_parser("ask", help="спитати, як пройшов день")
    p_ask.add_argument("--force", action="store_true", help="спитати навіть якщо вже відповів")

    p_cal = sub.add_parser("calibrate", help="порівняти прогноз із фактом і дописати правила")
    p_cal.add_argument("--day", help="типово — вчора")

    p_rules = sub.add_parser("rules", help="накопичені правила")
    p_rules.add_argument("--limit", type=int, default=8)

    args = ap.parse_args()

    if args.cmd == "add":
        day = date.fromisoformat(args.day) if args.day else today()
        add(args.text, day, args.source)
        print(f"записано за {day.isoformat()}")
    elif args.cmd == "list":
        day = date.fromisoformat(args.day) if args.day else None
        for r in remarks(day):
            print(f"{r['day']} {r['ts'][11:16]}  {r['text']}")
    elif args.cmd == "ask":
        ask(force=args.force)
    elif args.cmd == "calibrate":
        day = date.fromisoformat(args.day) if args.day else today() - timedelta(days=1)
        out = calibrate(day)
        print(out or "нічого не калібрував")
    elif args.cmd == "rules":
        print(rules(args.limit) or "правил поки немає")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
