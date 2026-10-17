#!/usr/bin/env python
"""Probe: weather in the configured city (wttr.in, no API key).

City and TTL come from config.json (`probes.weather`).
"""
import json, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

CITY = conf("probes.weather.city", "Lviv")
CITY_NAME = conf("probes.weather.display_name", CITY)
LANG = conf("locale.speech_language", "uk")
TTL = conf("probes.weather.ttl", 1800)
URL = f"https://wttr.in/{CITY}?format=j1&lang={LANG}"

try:
    with urllib.request.urlopen(URL, timeout=25) as r:
        d = json.load(r)
    cur = d["current_condition"][0]
    today = d["weather"][0]
    desc = (cur.get(f"lang_{LANG}") or [{}])[0].get("value") or cur["weatherDesc"][0]["value"]
    t, feels = int(cur["temp_C"]), int(cur["FeelsLikeC"])
    lo, hi = int(today["mintempC"]), int(today["maxtempC"])
    rain = max(int(h["chanceofrain"]) for h in today["hourly"])
    # heavy rain or hard frost is worth flagging, everything else is just information
    sev = "warn" if rain >= 70 or lo <= -10 else "info"
    print(json.dumps({
        "id": "weather", "ok": True, "severity": sev,
        "value": {"now_c": t, "feels_c": feels, "min_c": lo, "max_c": hi,
                  "rain_chance": rain, "desc": desc, "city": CITY},
        "text": f"{CITY_NAME}: зараз {t}°C (відчувається {feels}°C), {desc.lower()}; "
                f"удень від {lo} до {hi}°C, дощ {rain}%",
        "ttl": TTL}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"id": "weather", "ok": False, "severity": "warn",
                      "text": f"Погода недоступна: {e}", "ttl": 300}, ensure_ascii=False))
