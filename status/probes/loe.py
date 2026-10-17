#!/usr/bin/env python
"""Пробник: графік відключень для нашої черги (alerts.energy, статичний HTML)."""
import json, re, html, urllib.request, os

CHERGA = os.environ.get("LOE_CHERGA", "4.1")
URL = "https://alerts.energy/lvivska-oblast"

def lines_of(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", t)
    return [x.strip() for x in html.unescape(t).split("\n") if x.strip()]

try:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        page = r.read().decode("utf-8", "replace")
    L = lines_of(page)

    # журнал змін: HH:MM | джерело | дія | "Черга" | X.Y | ":" | старе | "→" | нове
    events = []
    for i, x in enumerate(L):
        if x == "Черга" and i + 4 < len(L) and L[i + 1] == CHERGA and L[i + 2] == ":":
            when = next((L[j] for j in range(i - 1, max(0, i - 5), -1)
                         if re.fullmatch(r"\d{2}:\d{2}", L[j])), "")
            old, new = L[i + 3], (L[i + 5] if L[i + 4] == "→" else "")
            action = next((L[j] for j in range(i - 1, max(0, i - 4), -1)
                           if "графік" in L[j]), "")
            events.append({"time": when, "action": action, "from": old, "to": new})
    events.sort(key=lambda e: e["time"], reverse=True)
    cur = events[0] if events else None
    sched = cur["to"] if cur and cur["to"] else (cur["from"] if cur else "")
    off = re.findall(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", sched)
    # головне питання — коли саме, тому рахуємо відносно поточного часу
    import datetime
    now = datetime.datetime.now()
    def at(hm):
        h, m = map(int, hm.split(":"))
        return now.replace(hour=h % 24, minute=m, second=0, microsecond=0) + (
            datetime.timedelta(days=1) if h >= 24 else datetime.timedelta())
    def human(delta):
        m = int(delta.total_seconds() // 60)
        return f"{m} хв" if m < 60 else f"{m // 60} год {m % 60:02d} хв"

    state = None
    for a, b in off:
        if at(a) <= now < at(b):
            state = f"зараз без світла, увімкнуть о {b} (через {human(at(b) - now)})"
            break
        if now < at(a):
            state = f"вимкнуть о {a} (через {human(at(a) - now)}), до {b}"
            break
    if off and not state:
        state = "на сьогодні відключення вже минули"

    text = (f"Світло: {state}. Сьогодні {sched}"
            if cur and off else
            f"Світло: відключень на сьогодні не заплановано (черга {CHERGA})")
    print(json.dumps({"id": "loe", "ok": True,
                      "severity": "warn" if off else "info",
                      "value": {"cherga": CHERGA, "schedule": sched, "intervals": off,
                                "updated": cur["time"] if cur else "", "events": events[:4]},
                      "text": text, "ttl": 900}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"id": "loe", "ok": False, "severity": "warn",
                      "text": f"Графік недоступний: {e}", "ttl": 300}, ensure_ascii=False))
