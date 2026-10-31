#!/usr/bin/env python
"""Noos tasks: an event log in tasks/tasks.jsonl, state rebuilt by replaying it.

  store.py add "полагодити індексацію до п'ятниці" [--project noos] [--min 90] [--deep] [--block]
  store.py add "перебрати акваріум на вихідних"     — період, без блоку в календарі
  store.py block <id> on|off        — чи ставити цю задачу блоком у календар Noos
  store.py link <id> <event_id> <початок> <кінець>   — прив'язати створену подію
  store.py unlink <id> <event_id>   — відв'язати (після видалення події)
  store.py events [<id>]            — показати події задач
  store.py list [--all]
  store.py done <id|частина назви>
  store.py defer <id|частина назви> "завтра"
  store.py edit <id> [--title "нова назва"] [--project x] [--min 90]
  store.py cancel <id|частина назви>
  store.py start <id|частина назви> — почав робити: пишемо факт у журнал
  store.py stop  <id|частина назви> — закінчив або відклав; рахуємо витрачений час
  store.py spent [<id>]             — план проти факту
  store.py similar "текст"          — скільки насправді займали схожі задачі
  store.py md                       — перезібрати tasks/open.md

The file is append-only: a correction is a new event, never an edit of an old one.
"""
import json, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

HOME = path("paths.home")
LOG = HOME / "tasks" / "tasks.jsonl"
VIEW = HOME / "tasks" / "open.md"

DAYS = {"понеділок": 0, "пн": 0, "вівторок": 1, "вт": 1, "середа": 2, "середу": 2, "ср": 2,
        "четвер": 3, "чт": 3, "п'ятниця": 4, "п'ятницю": 4, "пʼятницю": 4, "пт": 4,
        "субота": 5, "суботу": 5, "сб": 5, "неділя": 6, "неділю": 6, "нд": 6}
MONTHS = {"січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
          "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12}


def parse_period(text):
    """-> (period or None, text without the phrase). Period: (kind, start, end)."""
    low, t = text.lower(), text
    today = date.today()

    def cut(pattern):
        nonlocal t
        t = re.sub(pattern, " ", t, count=1, flags=re.I).strip(" ,.-")

    if re.search(r"\b(на\s+)?(вихідних|вікенд[іа]?|вихідні)\b", low):
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        cut(r"\b(на\s+)?(вихідних|вікенд[іа]?|вихідні)\b")
        return ("вихідні", sat, sat + timedelta(days=1)), t
    if re.search(r"\bнаступного\s+тижня\b", low):
        mon = today + timedelta(days=7 - today.weekday())
        cut(r"\bнаступного\s+тижня\b")
        return ("тиждень", mon, mon + timedelta(days=6)), t
    if re.search(r"\b(цього\s+)?тижня\b", low):
        cut(r"\b(цього\s+)?тижня\b")
        end = today + timedelta(days=6 - today.weekday())
        if end <= today:                      # неділя: «цього тижня» = наступні сім днів
            end = today + timedelta(days=7)
        return ("тиждень", today, end), t
    if re.search(r"\b(цього\s+)?місяця\b", low):
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        cut(r"\b(цього\s+)?місяця\b")
        return ("місяць", today, nxt - timedelta(days=1)), t
    return None, t


def parse_due(text):
    """-> (date or None, text without the time phrase). Parses Ukrainian wordings."""
    t = text
    low = t.lower()
    today = date.today()

    def cut(pattern):
        nonlocal t
        t = re.sub(pattern, " ", t, count=1, flags=re.I).strip(" ,.-")

    def cut_span(match):
        """Cut exactly the matched phrase, not the first match of the pattern elsewhere."""
        nonlocal t
        a, b = match.span()
        t = (t[:a] + " " + t[b:]).strip(" ,.-")
        t = re.sub(r"\s{2,}", " ", t)

    m = re.search(r"\b(сьогодні)\b", low)
    if m:
        cut(r"\bсьогодні\b"); return today, t
    m = re.search(r"\b(завтра)\b", low)
    if m:
        cut(r"\bзавтра\b"); return today + timedelta(days=1), t
    m = re.search(r"\b(післязавтра)\b", low)
    if m:
        cut(r"\bпіслязавтра\b"); return today + timedelta(days=2), t
    m = re.search(r"через\s+(\d+)\s+(дн|тижн)", low)
    if m:
        n = int(m.group(1)) * (7 if m.group(2) == "тижн" else 1)
        cut_span(m); return today + timedelta(days=n), t
    m = re.search(r"\b(?:до|у|в|на)\s+(\d{1,2})\s+(" + "|".join(MONTHS) + r")\b", low)
    if m:
        d, mo = int(m.group(1)), MONTHS[m.group(2)]
        y = today.year + (1 if (mo, d) < (today.month, today.day) else 0)
        cut_span(m); return date(y, mo, d), t
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", low)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3) or today.year)
        y += 2000 if y < 100 else 0
        try:
            when = date(y, mo, d)
        except ValueError:      # «python 3.14», «31.11» — a number, not a date (t1048)
            when = None
        if when:
            cut_span(m); return when, t
    m = re.search(r"\b(?:до|у|в|на)\s+(" + "|".join(map(re.escape, DAYS)) + r")\b", low)
    if m:
        want = DAYS[m.group(1)]
        ahead = (want - today.weekday()) % 7 or 7
        cut_span(m); return today + timedelta(days=ahead), t
    return None, t


def append(rec):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec["ts"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def state():
    """Replay the event log into current state."""
    tasks = {}
    if not LOG.exists():
        return tasks
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        tid, op = e.get("id"), e.get("op")
        if op == "add":
            tasks[tid] = {k: v for k, v in e.items() if k not in ("op",)}
            tasks[tid]["status"] = "open"
            tasks[tid]["created"] = e["ts"]
        elif tid in tasks:
            if op == "done":
                tasks[tid]["status"] = "done"; tasks[tid]["closed"] = e["ts"]
            elif op == "cancel":
                tasks[tid]["status"] = "cancelled"; tasks[tid]["closed"] = e["ts"]
            elif op == "defer":
                tasks[tid]["due"] = e.get("due"); tasks[tid]["status"] = "open"
            elif op == "start":
                tasks[tid].setdefault("runs", []).append({"from": e["ts"], "to": None})
                tasks[tid]["running"] = True
            elif op == "stop":
                runs = tasks[tid].setdefault("runs", [])
                if runs and runs[-1]["to"] is None:
                    runs[-1]["to"] = e["ts"]
                tasks[tid]["running"] = False
            elif op == "link":
                tasks[tid].setdefault("events", []).append(
                    {"event": e["event"], "start": e["start"], "end": e["end"],
                     "calendar": e.get("calendar", "noos"),
                     "kind": e.get("kind", "plan")})      # plan = booked, fact = happened
            elif op == "unlink":
                tasks[tid]["events"] = [x for x in tasks[tid].get("events", [])
                                        if x["event"] != e["event"]]
            elif op == "block":
                tasks[tid]["block"] = bool(e.get("block"))
            elif op == "edit":
                tasks[tid].update({k: v for k, v in e.items()
                                   if k in ("title", "project", "due", "estimate",
                                            "energy", "period", "block")})
    return tasks


def next_id(tasks):
    n = 1 + max([int(k[1:]) for k in tasks if re.fullmatch(r"t\d+", k)] or [0])
    return f"t{n:03d}"


def find(tasks, needle):
    if needle in tasks:
        return needle
    hits = [k for k, v in tasks.items()
            if needle.lower() in v["title"].lower() and v["status"] == "open"]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        sys.exit(f"не знайшов задачу: {needle}")
    sys.exit("неоднозначно — " + ", ".join(f"{k}: {tasks[k]['title']}" for k in hits))


def minutes(t):
    """Actual time spent, from the start/stop pairs in the log."""
    total = 0
    for r in t.get("runs") or []:
        try:
            a = datetime.fromisoformat(r["from"])
            b = datetime.fromisoformat(r["to"]) if r["to"] else datetime.now().astimezone()
            total += max(0, int((b - a).total_seconds() // 60))
        except Exception:
            continue
    return total


def fmt(t, tid):
    due = t.get("due")
    mark = ""
    if t.get("status") in ("done", "cancelled"):
        # for closed tasks the deadline is no longer news — show when it was done
        # the day the task was actually done, not when it got recorded
        closed = (t.get("due") or t.get("closed") or "")[:10]
        day = {date.today().isoformat(): "сьогодні",
               (date.today() - timedelta(days=1)).isoformat(): "вчора"}.get(closed, closed)
        proj = f" [{t['project']}]" if t.get("project") else ""
        return f"{tid}  {t['title']}{proj} · {day}"
    if t.get("period") and not due:
        kind, a, b = t["period"]
        a_, b_ = date.fromisoformat(a), date.fromisoformat(b)
        mark = (f" · {kind} {a_:%d.%m}" if a_ == b_ else f" · {kind} {a_:%d.%m}-{b_:%d.%m}")
    if due:
        d = date.fromisoformat(due)
        left = (d - date.today()).days
        mark = {0: " ⚠ сьогодні", 1: " · завтра"}.get(left, f" · {due}")
        if left < 0:
            mark = f" ‼ прострочено на {-left} дн"
    proj = f" [{t['project']}]" if t.get("project") else ""
    est = f" ~{t['estimate']}хв" if t.get("estimate") else ""
    blk = " 📌" if t.get("block") else ""      # 📌 = хоче блок часу
    spent = minutes(t)
    run = ""
    if t.get("running"):
        run = f" ▶ {spent} хв"
    elif spent:
        run = f" ⏱ {spent} хв"
    evs = [e for e in (t.get("events") or []) if e.get("kind", "plan") == "plan"]
    ev = ""
    if evs:
        nearest = min(e["start"] for e in evs)
        ev = f" 🗓 {nearest[8:10]}.{nearest[5:7]} {nearest[11:16]}" + (
            f" (+{len(evs) - 1})" if len(evs) > 1 else "")
    return f"{tid}  {t['title']}{proj}{mark}{est}{blk}{run}{ev}"


def write_view(tasks):
    openy = [(k, v) for k, v in tasks.items() if v["status"] == "open"]
    openy.sort(key=lambda kv: (kv[1].get("due") or "9999", kv[0]))
    lines = ["# Відкриті задачі", "",
             f"_оновлено {datetime.now():%Y-%m-%d %H:%M}, усього {len(openy)}_", ""]
    lines += [f"- `{k}` {fmt(v, '').strip()}" for k, v in openy] or ["- (порожньо)"]
    VIEW.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    tasks = state()

    if cmd == "add":
        flags = {}
        text_parts = []
        i = 0
        while i < len(rest):
            a = rest[i]
            if a == "--project" and i + 1 < len(rest):
                flags["project"] = rest[i + 1]; i += 2; continue
            if a == "--min" and i + 1 < len(rest):
                flags["estimate"] = int(rest[i + 1]); i += 2; continue
            if a == "--deep":
                flags["energy"] = "deep"; i += 1; continue
            if a == "--block":
                flags["block"] = True; i += 1; continue
            if a == "--period" and i + 1 < len(rest):
                flags["period_word"] = rest[i + 1]; i += 2; continue
            if a == "--source" and i + 1 < len(rest):
                flags["source"] = rest[i + 1]; i += 2; continue
            text_parts.append(a); i += 1
        raw = " ".join(text_parts)
        if flags.get("period_word"):
            raw = raw + " " + flags["period_word"]
        period, raw = parse_period(raw)
        due, title = parse_due(raw)
        tid = next_id(tasks)
        append({"op": "add", "id": tid, "title": title,
                "due": due.isoformat() if due else None,
                "period": ([period[0], period[1].isoformat(), period[2].isoformat()]
                           if period else None),
                "block": bool(flags.get("block")),
                "project": flags.get("project"), "estimate": flags.get("estimate"),
                "energy": flags.get("energy", "routine"),
                "source": flags.get("source", "telegram")})
        tasks = state(); write_view(tasks)
        print(fmt(tasks[tid], tid))

    elif cmd in ("done", "cancel"):
        tid = find(tasks, " ".join(rest))
        if tasks[tid].get("running"):      # closing also stops the clock
            append({"op": "stop", "id": tid})
        append({"op": cmd, "id": tid})
        tasks = state(); write_view(tasks)
        print(("закрито: " if cmd == "done" else "скасовано: ") + tasks[tid]["title"])

    elif cmd == "defer":
        tid = find(tasks, rest[0])
        phrase = " ".join(rest[1:])
        due, _ = parse_due(phrase)
        if phrase.strip() and not due:
            # writing due: null here silently wiped an existing deadline (t1048)
            sys.exit(f"не зрозумів дату «{phrase}» — дедлайн лишається як був")
        append({"op": "defer", "id": tid, "due": due.isoformat() if due else None})
        tasks = state(); write_view(tasks)
        print(fmt(tasks[tid], tid))

    elif cmd == "edit":
        # a correction is a new event, never a rewrite of an old line
        tid = find(tasks, rest[0])
        rec = {"op": "edit", "id": tid}
        i = 1
        while i < len(rest):
            a = rest[i]
            if a == "--title" and i + 1 < len(rest):
                rec["title"] = rest[i + 1]; i += 2
            elif a == "--project" and i + 1 < len(rest):
                rec["project"] = rest[i + 1]; i += 2
            elif a == "--min" and i + 1 < len(rest):
                rec["estimate"] = int(rest[i + 1]); i += 2
            else:
                i += 1
        if len(rec) == 2:
            sys.exit("нічого не змінено: вкажи --title, --project або --min")
        append(rec)
        tasks = state(); write_view(tasks)
        print(fmt(tasks[tid], tid))

    elif cmd == "block":
        tid = find(tasks, rest[0])
        on = (rest[1:2] or ["on"])[0] not in ("off", "ні", "0")
        append({"op": "block", "id": tid, "block": on})
        tasks = state(); write_view(tasks)
        print(("у календар: " if on else "без календаря: ") + tasks[tid]["title"])

    elif cmd in ("start", "stop"):
        tid = find(tasks, " ".join(rest))
        append({"op": cmd, "id": tid})
        tasks = state(); write_view(tasks)
        t = tasks[tid]
        if cmd == "start":
            est = t.get("estimate")
            hint = f" Плановано {est} хв." if est else ""
            print(f"почав: {t['title']}.{hint}")
        else:
            spent, est = minutes(t), t.get("estimate")
            diff = ""
            if est:
                d = spent - est
                diff = f" — {'довше' if d > 0 else 'швидше'} за план на {abs(d)} хв" if abs(d) >= 5 else " — рівно за планом"
            print(f"зупинив: {t['title']}. Витрачено {spent} хв{diff}")

    elif cmd == "spent":
        rows = [(k, v) for k, v in tasks.items() if minutes(v)]
        if rest:
            rows = [(k, v) for k, v in rows if k == find(tasks, " ".join(rest))]
        if not rows:
            print("факту ще немає — користуйся start/stop")
        for k, v in sorted(rows, key=lambda kv: -minutes(kv[1])):
            est = v.get("estimate")
            plan = f"план {est}" if est else "без плану"
            print(f"{k}  {v['title'][:46]:48} {plan:>10} | факт {minutes(v)} хв")

    elif cmd == "similar":
        """What comparable work actually took — the basis for the next estimate."""
        needle = set(w.lower() for w in " ".join(rest).split() if len(w) > 3)
        scored = []
        for k, v in tasks.items():
            spent = minutes(v)
            if not spent:
                continue
            words = set(w.lower() for w in v["title"].split() if len(w) > 3)
            overlap = len(needle & words)
            if overlap or (v.get("project") and v["project"] in " ".join(rest).lower()):
                scored.append((overlap, spent, k, v))
        if not scored:
            print("схожого з виміряним часом ще немає")
        for _, spent, k, v in sorted(scored, key=lambda x: (-x[0], -x[1]))[:5]:
            est = v.get("estimate") or 0
            print(f"{k}  {v['title'][:44]:46} план {est or '—':>4} | факт {spent} хв")

    elif cmd == "link":
        tid = find(tasks, rest[0])
        append({"op": "link", "id": tid, "event": rest[1],
                "start": rest[2], "end": rest[3],
                "calendar": rest[4] if len(rest) > 4 else "noos",
                "kind": rest[5] if len(rest) > 5 else "plan"})
        tasks = state(); write_view(tasks)
        print(fmt(tasks[tid], tid))

    elif cmd == "unlink":
        tid = find(tasks, rest[0])
        append({"op": "unlink", "id": tid, "event": rest[1]})
        tasks = state(); write_view(tasks)
        print(fmt(tasks[tid], tid))

    elif cmd == "events":
        sel = [find(tasks, rest[0])] if rest else [k for k, v in tasks.items()
                                                   if v.get("events") and v["status"] == "open"]
        if not sel:
            print("подій немає")
        for tid in sel:
            t = tasks[tid]
            print(f"{tid}  {t['title']}")
            for e in t.get("events", []):
                mark = "🗓" if e.get("kind", "plan") == "plan" else "✔"
                print(f"    {mark} {e['start']} → {e['end']}  [{e['calendar']}]  {e['event']}")

    elif cmd == "list":
        show_all = "--all" in rest
        rows = [(k, v) for k, v in tasks.items() if show_all or v["status"] == "open"]
        rows.sort(key=lambda kv: (kv[1].get("due") or "9999", kv[0]))
        if not rows:
            print("задач немає")
        for k, v in rows:
            flag = {"open": "", "done": " ✓", "cancelled": " ✗"}[v["status"]]
            print(fmt(v, k) + flag)

    elif cmd == "md":
        write_view(tasks); print(VIEW)

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
