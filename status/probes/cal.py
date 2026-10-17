#!/usr/bin/env python
"""Пробник: що в календарі від зараз до кінця наступного дня.

Файл називається cal.py, а не calendar.py, навмисно: інакше він перекриває
стандартний модуль calendar і ламає імпорт urllib.

Джерело — «секретна адреса в формaті iCal» з налаштувань Google Календаря
(Налаштування календаря → Інтеграція → Секретна адреса в формaті iCal).
Кладеться в `~/claude-home/.env.calendar`, по рядку на календар:
    CAL_особистий=https://calendar.google.com/calendar/ical/.../basic.ics
    CAL_сімейні=https://calendar.google.com/calendar/ical/.../basic.ics

Жодного OAuth: звичайний HTTPS-запит, тому працює і в headless-сесіях.
Повторювані події розкриваються через RRULE (python-dateutil).
"""
import json, re, sys
from urllib.request import urlopen
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

HOME = Path.home() / "claude-home"
ENV = HOME / ".env.calendar"
TZ = ZoneInfo("Europe/Kyiv")
HORIZON_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1


def out(**kw):
    kw.setdefault("id", "cal")
    kw.setdefault("ttl", 900)
    print(json.dumps(kw, ensure_ascii=False))
    sys.exit(0)


def env():
    cals = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("CAL_") and "=" in line:
                k, v = line.split("=", 1)
                cals[k[4:].strip()] = v.strip().strip('"').strip("'")
    return cals


def unfold(text):
    """У iCal довгі рядки переносяться пробілом на початку наступного."""
    return re.sub(r"\r?\n[ \t]", "", text)


def parse_dt(value, params):
    """DTSTART/DTEND -> (datetime у Києві, чи це цілий день)."""
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value, "%Y%m%d").replace(tzinfo=TZ)
        return d, True
    tzid = None
    m = re.search(r"TZID=([^:;]+)", params)
    if m:
        try:
            tzid = ZoneInfo(m.group(1))
        except Exception:
            tzid = None
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
    else:
        dt = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tzid or TZ)
    return dt.astimezone(TZ), False


def events(ics, lo, hi):
    """Події, що перетинаються з [lo, hi): звичайні і розкриті повторювані."""
    res = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold(ics), re.S):
        fields = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            key = name.split(";")[0].upper()
            fields.setdefault(key, (name[len(key):], value.strip()))
        if "DTSTART" not in fields:
            continue
        if (fields.get("STATUS") or ("", ""))[1] == "CANCELLED":
            continue
        summary = (fields.get("SUMMARY") or ("", "(без назви)"))[1]
        loc = (fields.get("LOCATION") or ("", ""))[1]
        sp, sv = fields["DTSTART"]
        start, allday = parse_dt(sv, sp)
        dur = timedelta(hours=1)
        if "DTEND" in fields:
            ep, ev = fields["DTEND"]
            end, _ = parse_dt(ev, ep)
            dur = end - start

        starts = []
        if "RRULE" in fields:
            rule = fields["RRULE"][1]
            try:
                excl = set()
                if "EXDATE" in fields:
                    for part in fields["EXDATE"][1].split(","):
                        excl.add(parse_dt(part.strip(), fields["EXDATE"][0])[0])
                for occ in rrulestr(rule, dtstart=start).between(
                        lo - dur, hi, inc=True):
                    if occ not in excl:
                        starts.append(occ)
            except Exception:
                starts = [start]
        else:
            starts = [start]

        for s in starts:
            if s + dur > lo and s < hi:
                res.append({"start": s, "allday": allday,
                            "summary": summary, "loc": loc})
    return res


cals = env()
if not cals:
    out(ok=False, severity="warn", ttl=3600,
        text="Календар: немає адрес. Поклади секретні iCal-посилання у "
             "~/claude-home/.env.calendar рядками CAL_назва=https://...")

now = datetime.now(TZ)
hi = (now + timedelta(days=HORIZON_DAYS)).replace(hour=23, minute=59, second=59)
items, broken = [], []

for name, url in cals.items():
    try:
        with urlopen(url, timeout=25) as r:
            ics = r.read().decode("utf-8", "replace")
        for e in events(ics, now, hi):
            e["cal"] = name
            items.append(e)
    except Exception as e:
        broken.append(f"{name}: {e}")

items.sort(key=lambda e: e["start"])

def label(e):
    s = e["start"]
    day = "сьогодні" if s.date() == now.date() else (
        "завтра" if s.date() == now.date() + timedelta(days=1) else s.strftime("%d.%m"))
    when = day if e["allday"] else f"{day} {s:%H:%M}"
    tail = f" ({e['loc']})" if e["loc"] else ""
    return f"  • {when} — {e['summary']}{tail}"

if not items:
    text = f"Календар: до кінця {'завтра' if HORIZON_DAYS else 'дня'} нічого"
    sev = "quiet"
else:
    text = "\n".join([f"Календар: {len(items)} подій"] + [label(e) for e in items[:10]])
    sev = "info"
if broken:
    text += "\n  ! не прочитано — " + "; ".join(broken)

out(ok=not broken, severity=sev,
    value={"count": len(items),
           "items": [{"start": e["start"].isoformat(), "summary": e["summary"],
                      "cal": e["cal"], "allday": e["allday"]} for e in items[:20]],
           "errors": broken},
    text=text)
