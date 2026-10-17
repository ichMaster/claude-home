#!/usr/bin/env python
"""Probe: air-raid alert for our location (region + district).

Region, district, source URL and TTL come from config.json (`probes.alarm`);
environment variables still win, so a one-off run can be pointed elsewhere.
"""
import json, os, sys, urllib.request, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

URL = conf("probes.alarm.url")
REGION = os.environ.get("ALARM_REGION", conf("probes.alarm.region"))
DISTRICT = os.environ.get("ALARM_DISTRICT", conf("probes.alarm.district"))
TTL = conf("probes.alarm.ttl", 60)


def ago(ts):
    """How long the alert has been on, in words."""
    if not ts:
        return ""
    t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    m = int((datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() // 60)
    return f"{m} хв" if m < 60 else f"{m//60} год {m%60} хв"


try:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    st = d["states"].get(REGION, {})
    districts = st.get("districts") or {}
    dist = districts.get(DISTRICT, {})
    on_region = bool(st.get("enabled"))
    on_dist = bool(dist.get("enabled"))
    since = ago(dist.get("enabled_at") or st.get("enabled_at"))
    elsewhere = sorted(k for k, v in d["states"].items() if v.get("enabled") and k != REGION)

    if on_dist or on_region:
        where = DISTRICT if on_dist else REGION
        text = f"🔴 Повітряна тривога: {where}" + (f", вже {since}" if since else "")
        sev = "alert"
    else:
        text = f"Тривоги немає: {REGION}"
        if elsewhere:
            text += (f" (в Україні зараз тривога в {len(elsewhere)} обл.: "
                     f"{', '.join(e.replace(' область','') for e in elsewhere[:4])})")
        sev = "info"
    print(json.dumps({"id": "alarm", "ok": True, "severity": sev,
                      "value": {"region": REGION, "district": DISTRICT,
                                "region_alert": on_region, "district_alert": on_dist,
                                "since": since, "elsewhere": elsewhere},
                      "text": text, "ttl": TTL}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"id": "alarm", "ok": False, "severity": "warn",
                      "text": f"Дані про тривоги недоступні: {e}", "ttl": TTL},
                     ensure_ascii=False))
