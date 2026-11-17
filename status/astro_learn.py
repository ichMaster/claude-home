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
        `--split` cuts a week of calendar into one entry per date — the model reads the
        headers, no pattern matching (t1033)
    astro_learn.py learn [--day 2026-10-31]      distil rules from the latest reference
    astro_learn.py rules [--limit 8]             what the prompts are currently obeying
    astro_learn.py list [--limit 5]              references on file
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "status"))
from noosconf import conf, path                                         # noqa: E402


INBOX = HOME / "status" / "state" / "astro-reference-inbox"


def store() -> Path:
    return Path(str(path("astro.reference", "status/state/astro-reference.jsonl")))


def consume(f: Path) -> Path | None:
    """Move an ingested file out of the inbox, so «чекають на внесення» stays honest.

    Nothing used to consume the inbox: a parked reference stayed listed as waiting after
    it was ingested, and the panel's «внести» could duplicate the store with every press
    (t1070). The raw text is kept — losing it was the original complaint (t1059) — it goes
    to `ingested/`, which the listings do not glob. Only a file that actually lives in the
    inbox moves; `add --file` on any other path leaves the owner's file where it is.
    """
    try:
        f = f.resolve()
        if f.parent != INBOX.resolve():
            return None
        done = f.parent / "ingested"
        done.mkdir(parents=True, exist_ok=True)
        target = done / f.name
        n = 1
        while target.exists():
            target = done / f"{f.stem}.{n}{f.suffix}"
            n += 1
        f.rename(target)
        return target
    except OSError as e:
        print(f"файл лишився в inbox ({e})", file=sys.stderr)
        return None


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


def ask(prompt: str, model: str = "", timeout: int = 180) -> str:
    """One model call, through the same headless path the forecast uses."""
    import mood                                                          # noqa: E402

    return mood.run_claude(prompt, model or str(conf("astro.models.layer", "sonnet")), timeout)


def split_days(text: str, first: date) -> list[tuple[date, str]]:
    """Cut a multi-day reference into one block per date — by the model, not by a pattern.

    He sends a week of hourly calendar at once, and comparing day against day only works if
    each day is stored under its own date. The headers are free-form prose in two languages
    («➲ Пт 30 октября», «31 жовтня», «завтра»), so the old regex plus month table missed
    anything it had not been shown and filed the whole week under one date — silently, which
    is the worst way to be wrong. The owner's standing rule settles it: content is read by
    the model, never parsed by a script (2026-10-31, said twice).

    Python's share is `json.loads` and `date.fromisoformat` — reading the model's structured
    answer, not the owner's content. A call that fails or answers unusably keeps the text
    whole under `first`: a reference stored in one piece beats a reference lost.
    """
    prompt = ((HOME / "status" / "mood" / "split.md").read_text(encoding="utf-8")
              .replace("{{СЬОГОДНІ}}", date.today().isoformat())
              .replace("{{ТИПОВА}}", first.isoformat())
              .replace("{{ТЕКСТ}}", text))
    try:
        raw = ask(prompt)
    except Exception as e:                                               # noqa: BLE001
        print(f"різати на дні не вдалось ({e}) — лишаю одним шматком", file=sys.stderr)
        return [(first, text.strip())]

    start, end = raw.find("["), raw.rfind("]")
    try:
        blocks = json.loads(raw[start:end + 1]) if start >= 0 < end else None
    except json.JSONDecodeError:
        blocks = None
    if not isinstance(blocks, list):
        return [(first, text.strip())]

    out: list[tuple[date, str]] = []
    for b in blocks:
        if not isinstance(b, dict) or not str(b.get("text", "")).strip():
            continue
        try:
            when = date.fromisoformat(str(b.get("day", "")))
        except ValueError:
            continue                              # a block we cannot date is not a day
        out.append((when, str(b["text"]).strip()))
    return out or [(first, text.strip())]


def for_day(day: date) -> str:
    """The latest reference for that date — what the morning pipeline cross-checks against."""
    refs = references(day)
    return refs[-1]["text"] if refs else ""


def covering(day: date) -> dict[str, str]:
    """His month and his year for that day — the two wider horizons (t1195).

    He publishes three: an hourly calendar for the day, a month, and a year. A monthly
    reference is stored under the first of its month and a yearly one under the first of its
    year, so «which one covers this day» is a comparison and not a search through prose. The
    latest record of each kind wins, which is what makes a corrected forward replace the one
    before it.
    """
    out: dict[str, str] = {}
    for rec in references():
        period = str(rec.get("period") or "")
        try:
            when = date.fromisoformat(str(rec.get("day") or ""))
        except ValueError:
            continue
        text = str(rec.get("text") or "").strip()
        if not text:
            continue
        if period == "місяць" and (when.year, when.month) == (day.year, day.month):
            out["місяць"] = text
        elif period == "рік" and when.year == day.year:
            out["рік"] = text
    return out


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
    """Our own reading for that day, as it was sent — through the one shared log parser.

    Hand-parsing the log with a hardcoded «--- підсумок ---» is what silently dropped the
    РОЗХОДЖЕННЯ comparison when t1126 renamed the sections (t1127)."""
    import mood                                                          # noqa: E402

    return mood.final_reading(day).strip()


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
    # `--file` so a reference parked by inbox.py (t1059) can be ingested without pushing a
    # few thousand characters through a command line
    p_add.add_argument("text", nargs="?", default="")
    p_add.add_argument("--file", help="взяти текст із файлу замість аргументу")
    p_add.add_argument("--day")
    p_add.add_argument("--author", default="")
    # `covering()` matches the exact strings, so anything else would be stored and never
    # found again — refused at the door instead (t1198)
    p_add.add_argument("--period", default="день",
                       choices=("день", "тиждень", "місяць", "рік"))
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
        # A month or a year is matched by the day it is stored under; today is a guess about
        # which month his forecast is for — a December text forwarded in late November would
        # feed November's mornings (t1198).
        if args.period in ("місяць", "рік") and not args.day:
            sys.exit("для --period місяць|рік вкажи --day — будь-який день того місяця чи року")
        text = args.text
        if getattr(args, "file", None):
            f = Path(args.file).expanduser()
            if not f.is_file():
                sys.exit(f"немає файлу {f}")
            text = f.read_text(encoding="utf-8")
        if not text.strip():
            sys.exit("порожній текст — нічого записувати")
        args.text = text
        parts = split_days(text, day) if args.split else [(day, text)]
        for when, body in parts:
            add(body, when, args.author, args.period)
            print(f"записано: {when} · {args.author or 'без автора'} · {len(body)} символів")
        if getattr(args, "file", None):
            # the store now holds the text, so the inbox copy is no longer "waiting";
            # moved before --learn, which is an extra on top of a completed ingest
            moved = consume(Path(args.file).expanduser())
            if moved:
                print(f"файл перенесено: {moved.parent.name}/{moved.name}")
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
