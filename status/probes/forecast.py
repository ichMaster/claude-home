#!/usr/bin/env python
"""Probe: the day's weather forecast for the configured city (wttr.in, no API key).

The `weather` probe says what it is like now; this one says how the day moves — morning,
afternoon and evening temperatures, when precipitation falls, the wind, sunrise and sunset.
It is written for the ear: no Latin script and no abbreviations, because every message is
spoken (see CLAUDE.md, the voice rules).

City comes from `probes.weather`, thresholds and the TTL from `probes.forecast`.
`summarize()` is pure so the shape of a day can be tested without the network.
"""
import json, sys, urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

# Parts of the day, as hours inclusive. The night is deliberately absent: the forecast is
# sent in the morning and nobody plans a night that has already passed.
PARTS = (("ранок", 6, 11), ("день", 12, 17), ("вечір", 18, 23))

# Sixteen compass points collapse to eight Ukrainian words — a forecast that distinguishes
# "північно-північно-східний" from "північно-східний" is precise about nothing anyone cares for.
DIRS = {
    "N": "північний", "NNE": "північний", "NE": "північно-східний", "ENE": "східний",
    "E": "східний", "ESE": "східний", "SE": "південно-східний", "SSE": "південний",
    "S": "південний", "SSW": "південний", "SW": "південно-західний", "WSW": "західний",
    "W": "західний", "WNW": "західний", "NW": "північно-західний", "NNW": "північний",
}


def _int(v, default=0):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _temp(v):
    """A temperature as it should be read aloud: 0 has no sign, everything else does."""
    return "0" if v == 0 else f"{v:+d}"


def _hour(slot):
    return _int(slot.get("time"), 0) // 100


def _desc(slot, lang):
    val = (slot.get(f"lang_{lang}") or [{}])[0].get("value")
    if not val:
        val = (slot.get("weatherDesc") or [{}])[0].get("value") or ""
    return val.strip()


def _clock(value):
    """'04:49 PM' -> '16:49'. Returns None on anything unexpected."""
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            return datetime.strptime((value or "").strip(), fmt).strftime("%-H:%M")
        except ValueError:
            continue
    return None


def _window(slots, key, threshold):
    """The first run of slots at or above the threshold, as (from_hour, to_hour, peak)."""
    best = None
    run = []
    for slot in slots:
        if _int(slot.get(key)) >= threshold:
            run.append(slot)
        elif run:
            best = best or run
            run = []
    best = best or run
    if not best:
        return None
    peak = max(_int(s.get(key)) for s in best)
    return _hour(best[0]), _hour(best[-1]) + 3, peak


def summarize(data, lang=None, city=None):
    """Turn a wttr.in `format=j1` response into a probe record."""
    lang = lang or conf("locale.speech_language", "uk")
    city = city or conf("probes.weather.display_name", conf("probes.weather.city", "Lviv"))
    ttl = conf("probes.forecast.ttl", 3600)
    precip_at = conf("probes.forecast.precip_chance", 50)
    warn_rain = conf("probes.forecast.warn_rain", 70)
    warn_gust = conf("probes.forecast.warn_gust", 60)
    warn_cold = conf("probes.forecast.warn_cold", -10)

    today = data["weather"][0]
    hourly = today.get("hourly") or []
    day = [s for s in hourly if 6 <= _hour(s) <= 23]
    pool = day or hourly

    lines = []
    counts = {}
    for s in pool:
        d = _desc(s, lang)
        if d:
            counts[d] = counts.get(d, 0) + 1
    head = max(counts, key=lambda d: counts[d]) if counts else ""
    lines.append(f"{city}, прогноз на сьогодні: {head.lower()}." if head
                 else f"{city}, прогноз на сьогодні.")

    # Temperatures, one phrase per part of the day that we actually have slots for.
    phrases = []
    for name, lo_h, hi_h in PARTS:
        vals = [_int(s.get("tempC")) for s in hourly if lo_h <= _hour(s) <= hi_h]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        phrases.append(f"{name} {_temp(lo)}" if lo == hi
                       else f"{name} від {_temp(lo)} до {_temp(hi)}")
    if phrases:
        lines.append("Температура: " + ", ".join(phrases) + " градусів.")

    # Feels-like is worth a word only when it differs enough to change what you wear.
    feels = [_int(s.get("FeelsLikeC")) for s in pool]
    temps = [_int(s.get("tempC")) for s in pool]
    if feels and temps and min(temps) - min(feels) >= 3:
        lines.append(f"Відчуватиметься як {_temp(min(feels))}.")

    rain = _window(pool, "chanceofrain", precip_at)
    snow = _window(pool, "chanceofsnow", precip_at)
    precip = []
    for label, win in (("Дощ", rain), ("Сніг", snow)):
        if win:
            a, b, peak = win
            end = "півночі" if b >= 24 else f"{b}:00"
            precip.append(f"{label} з {a}:00 до {end}, ймовірність до {peak} відсотків.")
    lines.extend(precip or ["Опадів не видно."])

    if pool:
        wind = max(_int(s.get("windspeedKmph")) for s in pool)
        gust = max(_int(s.get("WindGustKmph")) for s in pool)
        strongest = max(pool, key=lambda s: _int(s.get("windspeedKmph")))
        direction = DIRS.get((strongest.get("winddir16Point") or "").strip(), "")
        line = " ".join(x for x in ("Вітер", direction, f"до {wind} кілометрів на годину") if x)
        if gust >= wind + 10:
            line += f", пориви до {gust}"
        lines.append(line + ".")
    else:
        wind = gust = 0

    extras = []
    morning = [s for s in hourly if 6 <= _hour(s) <= 11]
    if morning and max(_int(s.get("chanceoffrost")) for s in morning) >= precip_at:
        extras.append("Уранці приморозок.")
    if pool and max(_int(s.get("chanceofthunder")) for s in pool) >= 30:
        extras.append("Можлива гроза.")
    if pool and max(_int(s.get("chanceoffog")) for s in pool) >= precip_at:
        extras.append("Туман.")
    lines.extend(extras)

    astro = (today.get("astronomy") or [{}])[0]
    sunrise, sunset = _clock(astro.get("sunrise")), _clock(astro.get("sunset"))
    if sunrise and sunset:
        lines.append(f"Світає о {sunrise}, сутеніє о {sunset}.")

    rain_peak = max((_int(s.get("chanceofrain")) for s in pool), default=0)
    lo_all = min((_int(s.get("tempC")) for s in pool), default=0)
    sev = "warn" if (rain_peak >= warn_rain or gust >= warn_gust or lo_all <= warn_cold) else "info"

    return {
        "id": "forecast", "ok": True, "severity": sev,
        "value": {"date": today.get("date"), "min_c": _int(today.get("mintempC")),
                  "max_c": _int(today.get("maxtempC")), "rain_chance": rain_peak,
                  "wind_kmph": wind, "gust_kmph": gust,
                  "sunrise": sunrise, "sunset": sunset, "city": city},
        "text": "\n".join(lines),
        "ttl": ttl,
    }


def main():
    city = conf("probes.weather.city", "Lviv")
    lang = conf("locale.speech_language", "uk")
    url = f"https://wttr.in/{city}?format=j1&lang={lang}"
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            data = json.load(r)
        print(json.dumps(summarize(data), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"id": "forecast", "ok": False, "severity": "warn",
                          "text": f"Прогноз погоди недоступний: {e}", "ttl": 300},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
