#!/usr/bin/env python
"""Probe: power-outage schedule for our grid queue (alerts.energy, static HTML).

Queue, source URL and TTL come from config.json (`probes.loe`); LOE_CHERGA still
overrides the queue for a one-off run.
"""
import json, re, html, urllib.request, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

CHERGA = os.environ.get("LOE_CHERGA", conf("probes.loe.queue"))
URL = conf("probes.loe.url")
TTL = conf("probes.loe.ttl", 900)

def lines_of(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", t)
    return [x.strip() for x in html.unescape(t).split("\n") if x.strip()]

try:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        page = r.read().decode("utf-8", "replace")
    L = lines_of(page)

    # change log on the page: HH:MM | source | action | "Черга" | X.Y | ":" | old | "→" | new
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
    # the question that matters is "when", so everything is relative to now
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
                      "text": text, "ttl": TTL}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"id": "loe", "ok": False, "severity": "warn",
                      "text": f"Графік недоступний: {e}", "ttl": 300}, ensure_ascii=False))
