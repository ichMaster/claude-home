#!/usr/bin/env python
"""Learn from a real astrologer's readings.

The owner follows an astrologer he rates as genuinely accurate and wants to feed those
readings in, so our own pipeline learns **what to look at and how to interpret it**
(2026-10-30: «я буду ще їй давати прогноз від іншого Астролога, реального і він дуже точний
і тому я хочу щоб Зірка вчилась на що звертати увагу і як саме інтерпретувати»).

**Only the interpretation is learned, never the style** (2026-10-30: «стиль у нього значно
гірше, тут важливо як він інтерпретує факти»). Two lessons come out of one text:

* **ТРАКТУВАННЯ** — how he gets from a factor to a meaning: which factor he calls loud,
  which he drops, which area of life he lands it in. For the hourly-calendar genre he sends
  (Moon by sign and house, void-of-course windows, timed Moon aspects weighted by the number
  of `✤`), this comes out as a vocabulary: factor → meaning, line by line.
* **РОЗХОДЖЕННЯ** — where his meaning for the same day differs from ours: a factor he leads
  with that we ranked as background, an area of life he names and we never mention, the same
  factor read the opposite way. This needs both texts for the same date.

Both end up as `ПРАВИЛО:` lines in `status/state/astro-reference-rules.md`, append-only like
every other log here: a rule that proves wrong is superseded by a new line, never edited
away. `rules()` feeds the newest of them into the weighing, the draft and the summary, beside
the calibration rules learned from his own account of his days — a reference reading says how
to read, his own feedback says whether we got him right, and neither replaces the other.

**What is deliberately NOT done:** the reference text never goes into a forecast as content.
Repeating another astrologer's sentences would be copying, not learning, and the two readings
are built from different things — his from a sun sign, ours from this chart's houses and
transits. Only the rules carry over.

    astro_learn.py add "<текст>" [--day …] [--author …] [--period …] [--split] [--learn]
        `--split` cuts a week of calendar into one entry per date, by its day headers
    astro_learn.py learn [--day 2026-10-31]      distil rules from the latest reference
    astro_learn.py rules [--limit 8]             what the prompts are currently obeying
    astro_learn.py list [--limit 5]              references on file
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "status"))
from noosconf import conf, path                                         # noqa: E402


def store() -> Path:
    return Path(str(path("astro.reference", "status/state/astro-reference.jsonl")))


def rules_file() -> Path:
    return Path(str(path("astro.reference_rules", "status/state/astro-reference-rules.md")))


def add(text: str, day: date, author: str = "", period: str = "день") -> None:
    f = store()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                             "day": day.isoformat(), "author": author.strip(),
                             "period": period, "text": text.strip()},
                            ensure_ascii=False) + "\n")


# "➲ Пт 30 октября", "Вс 1 ноября", "Пн 03 ноя" — the day headers of the hourly calendar
_MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6, "июл": 7,
           "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
           "січ": 1, "лют": 2, "бер": 3, "кві": 4, "тра": 5, "чер": 6, "лип": 7, "сер": 8,
           "вер": 9, "жов": 10, "лис": 11, "гру": 12}
_DAY_HEAD = re.compile(
    r"^[\s➲►▶*#>]*(?:пн|вт|ср|чт|пт|сб|вс|нд|пон|сер|пʼя|суб|нед)?[а-яіїєґ]*\.?\s*"
    r"(\d{1,2})\s*([а-яіїєґ]{3,10})\.?\s*$",
    re.IGNORECASE | re.MULTILINE)


def split_days(text: str, first: date) -> list[tuple[date, str]]:
    """Cut a multi-day calendar into one block per date.

    He sends the reference a week ahead (2026-10-31), and comparing day against day only
    works if each day is stored under its own date. Headers carry a day and a month name but
    no year, so the year is taken from `first` and rolled forward when the month wraps.
    """
    heads = list(_DAY_HEAD.finditer(text))
    if not heads:
        return [(first, text.strip())]
    out: list[tuple[date, str]] = []
    year = first.year
    prev_month = None
    for i, m in enumerate(heads):
        mon = None
        key = m.group(2).lower()[:3]
        if key in _MONTHS:
            mon = _MONTHS[key]
        if mon is None:
            continue
        if prev_month is not None and mon < prev_month:
            year += 1                             # the week crossed into January
        prev_month = mon
        try:
            when = date(year, mon, int(m.group(1)))
        except ValueError:
            continue
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if body.strip():
            out.append((when, body.strip()))
    return out or [(first, text.strip())]


def for_day(day: date) -> str:
    """The latest reference for that date — what the morning pipeline cross-checks against."""
    refs = references(day)
    return refs[-1]["text"] if refs else ""


def references(day: date | None = None) -> list[dict]:
    f = store()
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if day is None or rec.get("day") == day.isoformat():
            out.append(rec)
    return out


def ours(day: date) -> str:
    """Our own reading for that day, from the forecast log — the summary block only, which is
    the part that claims anything."""
    log = Path(str(path("astro.log", "status/state/mood.log")))
    if not log.is_file():
        return ""
    blocks = log.read_text(encoding="utf-8").split(f"===== {day.isoformat()} =====")
    if len(blocks) < 2:
        return ""
    block = blocks[1].split("=====")[0]
    if "--- підсумок ---" not in block:
        return ""
    return block.split("--- підсумок ---")[1].split("--- біоритми ---")[0].strip()


def learn(day: date | None = None) -> str:
    """Distil rules out of the latest reference for that day. Returns what was appended."""
    import mood                                                          # noqa: E402

    day = day or date.today()
    refs = references(day)
    if not refs:
        return ""
    ref = refs[-1]
    mine = ours(day)
    prompt = ((HOME / "status" / "mood" / "reference.md").read_text(encoding="utf-8")
              .replace("{{ДАТА}}", day.isoformat())
              .replace("{{АВТОР}}", ref.get("author") or "невідомий астролог")
              .replace("{{ПЕРІОД}}", ref.get("period", "день"))
              .replace("{{ЕТАЛОН}}", ref["text"])
              .replace("{{НАШЕ}}", mine or "(нашого читання за цей день немає)"))
    out = mood.plain(mood.run_claude(prompt, str(conf("astro.models.layer", "sonnet")),
                                     mood.CALL_TIMEOUT))
    if not out:
        return ""
    f = rules_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n===== {day.isoformat()} · {ref.get('author') or 'без автора'} "
                 f"({ref.get('period', 'день')}) =====\n{out}\n")
    return out


def rules(limit: int = 6) -> str:
    """The newest `ПРАВИЛО:` lines — this is what the prompts receive."""
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


def main() -> int:
    ap = argparse.ArgumentParser(description="навчання на прогнозах реального астролога")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="записати еталонний прогноз")
    p_add.add_argument("text")
    p_add.add_argument("--day")
    p_add.add_argument("--author", default="")
    p_add.add_argument("--period", default="день")
    p_add.add_argument("--learn", action="store_true", help="одразу витягти правила")
    p_add.add_argument("--split", action="store_true",
                       help="порізати багатоденний текст на дні за заголовками")

    p_learn = sub.add_parser("learn", help="витягти правила з еталона")
    p_learn.add_argument("--day")

    p_rules = sub.add_parser("rules", help="правила, які діють")
    p_rules.add_argument("--limit", type=int, default=6)

    p_list = sub.add_parser("list", help="що вже записано")
    p_list.add_argument("--limit", type=int, default=5)

    args = ap.parse_args()
    day = date.fromisoformat(args.day) if getattr(args, "day", None) else date.today()

    if args.cmd == "add":
        parts = split_days(args.text, day) if args.split else [(day, args.text)]
        for when, body in parts:
            add(body, when, args.author, args.period)
            print(f"записано: {when} · {args.author or 'без автора'} · {len(body)} символів")
        if args.learn:
            # learn from the day that is actually coming: a week of references at once would
            # be a week of calls, and only today's can be compared with our own reading
            for when, _ in parts:
                if when >= date.today():
                    out = learn(when)
                    print(f"--- {when} ---\n{out or 'правил не вийшло'}")
                    break
            else:
                out = learn(parts[-1][0])
                print(out or "правил не вийшло")
        return 0
    if args.cmd == "learn":
        out = learn(day)
        print(out or "еталона за цей день немає")
        return 0
    if args.cmd == "rules":
        print(rules(args.limit) or "правил поки немає")
        return 0
    for r in references()[-args.limit:]:
        print(f"{r['day']} · {r.get('author') or 'без автора'} · {r.get('period', 'день')} · "
              f"{len(r['text'])} символів")
        print(f"   {r['text'][:160]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
