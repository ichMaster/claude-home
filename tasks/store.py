#!/usr/bin/env python
"""Задачі Нооса: журнал подій у tasks/tasks.jsonl, стан збирається відтворенням.

  store.py add "полагодити індексацію до п'ятниці" [--проєкт noos] [--хв 90] [--глибока] [--блок]
  store.py add "перебрати акваріум на вихідних"     — період, без блоку в календарі
  store.py block <id> on|off        — чи ставити цю задачу блоком у календар Noos
  store.py link <id> <event_id> <початок> <кінець>   — прив'язати створену подію
  store.py unlink <id> <event_id>   — відв'язати (після видалення події)
  store.py events [<id>]            — показати події задач
  store.py list [--усі]
  store.py done <id|частина назви>
  store.py defer <id|частина назви> "завтра"
  store.py cancel <id|частина назви>
  store.py md                       — перезібрати tasks/open.md

Файл лише дозаписується: виправлення — новою подією, не правкою старої.
"""
import json, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path

HOME = Path.home() / "claude-home"
LOG = HOME / "tasks" / "tasks.jsonl"
VIEW = HOME / "tasks" / "open.md"

DAYS = {"понеділок": 0, "пн": 0, "вівторок": 1, "вт": 1, "середа": 2, "середу": 2, "ср": 2,
        "четвер": 3, "чт": 3, "п'ятниця": 4, "п'ятницю": 4, "пʼятницю": 4, "пт": 4,
        "субота": 5, "суботу": 5, "сб": 5, "неділя": 6, "неділю": 6, "нд": 6}
MONTHS = {"січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
          "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12}


def parse_period(text):
    """-> (період або None, текст без фрази). Період: (вид, початок, кінець)."""
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
    """-> (дата або None, текст без часової фрази). Розбирає українські формулювання."""
    t = text
    low = t.lower()
    today = date.today()

    def cut(pattern):
        nonlocal t
        t = re.sub(pattern, " ", t, count=1, flags=re.I).strip(" ,.-")

    def cut_span(match):
        """Вирізати саме знайдену фразу, а не перший збіг шаблону деінде."""
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
        cut_span(m); return date(y, mo, d), t
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
    """Відтворити поточний стан із журналу подій."""
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
            elif op == "link":
                tasks[tid].setdefault("events", []).append(
                    {"event": e["event"], "start": e["start"], "end": e["end"],
                     "calendar": e.get("calendar", "noos")})
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


def fmt(t, tid):
    due = t.get("due")
    mark = ""
    if t.get("status") in ("done", "cancelled"):
        # для закритих дедлайн уже не новина — показуємо, коли саме закрито
        # коли задачу зробили, а не коли я встиг її записати
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
    evs = t.get("events") or []
    ev = ""
    if evs:
        nearest = min(e["start"] for e in evs)
        ev = f" 🗓 {nearest[8:10]}.{nearest[5:7]} {nearest[11:16]}" + (
            f" (+{len(evs) - 1})" if len(evs) > 1 else "")
    return f"{tid}  {t['title']}{proj}{mark}{est}{blk}{ev}"


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
            if a == "--проєкт" and i + 1 < len(rest):
                flags["project"] = rest[i + 1]; i += 2; continue
            if a == "--хв" and i + 1 < len(rest):
                flags["estimate"] = int(rest[i + 1]); i += 2; continue
            if a == "--глибока":
                flags["energy"] = "deep"; i += 1; continue
            if a == "--блок":
                flags["block"] = True; i += 1; continue
            if a == "--період" and i + 1 < len(rest):
                flags["period_word"] = rest[i + 1]; i += 2; continue
            if a == "--джерело" and i + 1 < len(rest):
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
        append({"op": cmd, "id": tid})
        tasks = state(); write_view(tasks)
        print(("закрито: " if cmd == "done" else "скасовано: ") + tasks[tid]["title"])

    elif cmd == "defer":
        tid = find(tasks, rest[0])
        due, _ = parse_due(" ".join(rest[1:]))
        append({"op": "defer", "id": tid, "due": due.isoformat() if due else None})
        tasks = state(); write_view(tasks)
        print(fmt(tasks[tid], tid))

    elif cmd == "block":
        tid = find(tasks, rest[0])
        on = (rest[1:2] or ["on"])[0] not in ("off", "ні", "0")
        append({"op": "block", "id": tid, "block": on})
        tasks = state(); write_view(tasks)
        print(("у календар: " if on else "без календаря: ") + tasks[tid]["title"])

    elif cmd == "link":
        tid = find(tasks, rest[0])
        append({"op": "link", "id": tid, "event": rest[1],
                "start": rest[2], "end": rest[3],
                "calendar": rest[4] if len(rest) > 4 else "noos"})
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
                print(f"    🗓 {e['start']} → {e['end']}  [{e['calendar']}]  {e['event']}")

    elif cmd == "list":
        show_all = "--усі" in rest
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
