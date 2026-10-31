#!/usr/bin/env python
"""Probe: today's biorhythms — the arithmetic half of the morning, on its own.

Split out of the `mood` probe (t1061). The whole design keeps the two readings apart —
two calls, two messages, two voices, and the biorhythm prompt is forbidden to name a
planet — because merged into one verdict it stops being visible which claim came from
where (the owner, 2026-10-27, and again 2026-10-31: «не мішай гороскоп і біоритми в один
прогноз»). The probe was the one place that glued them back together, appending the three
figures to the astrology summary in a single `text`.

Reads nothing new and calls no model: `status/mood.py` computes this once a morning and
caches it in `astro.state`. A state file from an earlier day means the morning run has not
happened yet — `ok` stays true, because a missing reading is not a fault.
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

    figures = st.get("biorhythms") or ""
    if st.get("day") != today or not figures:
        out = {"id": "bio", "ok": True, "severity": "info",
               "value": {"day": st.get("day"), "fresh": False},
               "text": "Біоритми на сьогодні ще не рахувались", "ttl": TTL}
    else:
        conclusion = (st.get("bio_conclusion") or "").strip()
        out = {"id": "bio", "ok": True, "severity": "info",
               "value": {"day": st["day"], "fresh": True, "biorhythms": figures,
                         "conclusion": conclusion},
               "text": f"Біоритми: {figures}" + (f"\n{conclusion}" if conclusion else ""),
               "ttl": TTL}
except Exception as e:
    out = {"id": "bio", "ok": False, "severity": "warn", "value": None,
           "text": f"Біоритми недоступні: {e}", "ttl": 300}

print(json.dumps(out, ensure_ascii=False))
