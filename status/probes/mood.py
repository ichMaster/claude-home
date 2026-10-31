#!/usr/bin/env python
"""Probe: the mood of the day — today's horoscope, as it was already read.

Reads nothing new and calls no model: the reading is produced once a morning by
`status/mood.py` (timer `noos-mood`) and cached in `astro.state`. This probe only shows
it, so `/mood`, the digest and the watcher can repeat the day's resolution without
paying for a second reading.

A state file from an earlier day means the morning run has not happened yet — `ok` stays
true (a missing horoscope is not a fault), the text says so.
"""
import json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

TTL = conf("astro.ttl", 1800)

try:
    today = datetime.now(ZoneInfo(conf("astro.tz", "Europe/Kyiv"))).date().isoformat()
    f = path("astro.state")
    st = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}

    if st.get("day") != today:
        out = {"id": "mood", "ok": True, "severity": "info",
               "value": {"day": st.get("day"), "fresh": False},
               "text": "Прогноз на сьогодні ще не читався", "ttl": TTL}
    else:
        # Astrology only. The biorhythms have their own probe (`bio`, t1061): appending the
        # three figures here was the one place in the system that merged the two readings
        # back into one, which is exactly what the owner asked not to happen — merged, it
        # stops being visible which claim came from where.
        body = (st.get("summary") or "").strip()
        out = {"id": "mood", "ok": True, "severity": "info",
               "value": {"day": st["day"], "fresh": bool(body)},
               "text": body or "Прогноз на сьогодні ще не читався", "ttl": TTL}
except Exception as e:
    out = {"id": "mood", "ok": False, "severity": "warn", "value": None,
           "text": f"Прогноз недоступний: {e}", "ttl": 300}

print(json.dumps(out, ensure_ascii=False))
