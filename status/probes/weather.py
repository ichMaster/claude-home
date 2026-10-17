#!/usr/bin/env python
"""Пробник: погода у Львові (wttr.in, без ключа)."""
import json, urllib.request

URL = "https://wttr.in/Lviv?format=j1&lang=uk"
try:
    with urllib.request.urlopen(URL, timeout=25) as r:
        d = json.load(r)
    cur = d["current_condition"][0]
    today = d["weather"][0]
    desc = (cur.get("lang_uk") or [{}])[0].get("value") or cur["weatherDesc"][0]["value"]
    t, feels = int(cur["temp_C"]), int(cur["FeelsLikeC"])
    lo, hi = int(today["mintempC"]), int(today["maxtempC"])
    rain = max(int(h["chanceofrain"]) for h in today["hourly"])
    sev = "warn" if rain >= 70 or lo <= -10 else "info"
    print(json.dumps({
        "id": "weather", "ok": True, "severity": sev,
        "value": {"now_c": t, "feels_c": feels, "min_c": lo, "max_c": hi,
                  "rain_chance": rain, "desc": desc},
        "text": f"Львів: зараз {t}°C (відчувається {feels}°C), {desc.lower()}; "
                f"удень від {lo} до {hi}°C, дощ {rain}%",
        "ttl": 1800}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"id": "weather", "ok": False, "severity": "warn",
                      "text": f"Погода недоступна: {e}", "ttl": 300}, ensure_ascii=False))
