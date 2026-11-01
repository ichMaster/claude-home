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
    rows = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:    # a torn line (several appenders, no locking) — skip,
            continue                    # or ask/calibrate crash forever (t1047)
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


def questions(items: list[dict]) -> str:
    """The evening question, built straight from the morning's claims — no model involved.

    The owner's shape (2026-11-01): «десь в такому стилі треба б було питати про день, який
    пройшов». One yes/no per claim, each naming the window it was promised for and the sign
    it was promised by, in the forecast's own words, and an invitation to say it missed —
    «не влучило» is more useful than «нормально». No claims means no question: inventing one
    out of nothing is worse than silence.
    """
    if not items:
        return ""
    sys.path.insert(0, str(HOME / "status"))
    import mood  # noqa: E402
    head = ("Одне питання про сьогоднішнє." if len(items) == 1
            else f"{'Два' if len(items) == 2 else 'Три'} питання про сьогоднішнє.")
    lines = [head]
    for i, item in enumerate(items, 1):
        # `_unlabel` again at read time: rows stored before the parser learned to strip a
        # column name are still on disk, and «ознака:» must not be read aloud (t1126).
        window = mood._unlabel(str(item.get("window") or ""))
        claim = mood._unlabel(str(item.get("claim") or "")).rstrip(".")
        sign = mood._unlabel(str(item.get("sign") or "")).rstrip(".")
        order = ("Перше" if i == 1 else "Друге" if i == 2 else "Третє")
        variants = [mood._unlabel(v) for v in (item.get("variants") or [])
                    if str(v).strip()]
        if len(variants) > 1:
            shown = ", або ".join(v.rstrip(".") for v in variants)
            lines.append(f"{order}: {window} — {claim}. Як це вийшло: {shown}? "
                         "Чи нічого з цього?")
        else:
            lines.append(f"{order}: {window} — чи було так, що {claim}"
                         + (f"; {sign}" if sign else "") + "?")
    lines.append("Якщо жодного такого відчуття не було — так і скажи, це корисніше за "
                 "«нормально».")
    return "\n\n".join(lines)


def question_for(day: date) -> str:
    """This evening's question: the day's own claims, or the generic one if there were none.

    Deterministic by design since t1126 — the claims already carry the window and the sign,
    so a model call could only paraphrase them, and paraphrasing is where a promise turns
    back into atmosphere.
    """
    sys.path.insert(0, str(HOME / "status"))
    import mood  # noqa: E402

    # No claims means no question (t1126): the day either had promises to check or it did
    # not, and «як пройшов день» gets the generic answer it deserves. The generic form stays
    # for the days before the claims existed.
    return questions(mood.load_claims(day)) or QUESTION


def score_rows(rows: list[dict]) -> dict:
    """Hits, misses and the hit rate over the given claim records.

    `verified` is True, False or None: None means the evening never answered that one, and it
    counts in neither direction — a rate computed over silence would be the same kind of
    decoration the old reading was (t1126).
    """
    # `verified` is None (unanswered), False (nothing of the sort), or truthy — True, or the
    # name of the variant that actually landed (t1126).
    hits = sum(1 for r in rows
               if r.get("verified") not in (None, False) and r.get("verified") != "")
    misses = sum(1 for r in rows if r.get("verified") is False)
    unanswered = sum(1 for r in rows
                     if r.get("verified") is None or r.get("verified") == "")
    answered = hits + misses
    return {"hits": hits, "misses": misses, "unanswered": unanswered,
            "total": len(rows), "rate": (hits / answered) if answered else None}


def score(days: int | None = None) -> dict:
    """The same, over the last `astro.score_days` days of stored claims."""
    sys.path.insert(0, str(HOME / "status"))
    import mood  # noqa: E402

    span = int(days or conf("astro.score_days", 14))
    first = (today() - timedelta(days=span)).isoformat()
    rows = [r for r in mood._claim_rows(mood.claims_file())
            if str(r.get("day", "")) >= first]
    got = score_rows(rows)
    got["days"] = span
    return got


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

    p_score = sub.add_parser("score", help="влучність прогнозів за останні дні")
    p_score.add_argument("--days", type=int)

    args = ap.parse_args()

    if args.cmd == "score":
        got = score(args.days)
        if got["rate"] is None:
            print(f"за {got['days']} дн: {got['total']} прогнозів, "
                  f"жоден не підтверджений і не відкинутий — немає даних")
            return 0
        print(f"за {got['days']} дн: влучність {got['rate']*100:.0f}% "
              f"({got['hits']} влучило, {got['misses']} ні, "
              f"{got['unanswered']} без відповіді, усього {got['total']})")
        return 0

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
