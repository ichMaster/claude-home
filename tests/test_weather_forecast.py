"""t1141 — the day's weather forecast (status/probes/forecast.py).

The probe is spoken aloud, so the tests check the shape of the sentence as much as the
numbers: all three parts of the day named, a precipitation window with real hours, and not a
single Latin letter anywhere in the text.
"""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "data" / "wttr-lviv.json"

spec = importlib.util.spec_from_file_location("forecast_probe", ROOT / "status" / "probes" / "forecast.py")
forecast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forecast)


def load():
    return json.loads(FIXTURE.read_text())


def slot(hour, **over):
    base = {"time": f"{hour}00", "tempC": "5", "FeelsLikeC": "5", "windspeedKmph": "10",
            "WindGustKmph": "12", "winddir16Point": "W", "chanceofrain": "0",
            "chanceofsnow": "0", "chanceoffrost": "0", "chanceofthunder": "0",
            "chanceoffog": "0", "lang_uk": [{"value": "Мінлива хмарність"}]}
    base.update({k: str(v) for k, v in over.items()})
    return base


def day(slots, sunrise="07:30 AM", sunset="04:50 PM"):
    return {"weather": [{"date": "2026-11-09", "mintempC": "0", "maxtempC": "7",
                         "astronomy": [{"sunrise": sunrise, "sunset": sunset}],
                         "hourly": slots}]}


# TC1 — the real response reads as a forecast and carries no Latin script.
def test_real_response_reads_as_a_forecast():
    r = forecast.summarize(load())
    assert r["ok"] and r["id"] == "forecast"
    text = r["text"]
    for part in ("ранок", "день", "вечір"):
        assert part in text
    assert "Вітер" in text
    assert re.search(r"Світає о \d{1,2}:\d{2}, сутеніє о \d{1,2}:\d{2}\.", text)
    assert not re.search(r"[A-Za-z]", text), text
    assert r["value"]["sunrise"] == "7:26" and r["value"]["sunset"] == "16:49"


# TC2 — rain gets a window and raises the severity; a dry day says so and stays info.
def test_rain_window_and_severity():
    slots = [slot(h, chanceofrain=80 if 15 <= h <= 21 else 0) for h in range(0, 24, 3)]
    r = forecast.summarize(day(slots))
    assert "Дощ з 15:00 до півночі, ймовірність до 80 відсотків." in r["text"]
    assert r["severity"] == "warn"


def test_dry_day_is_quiet():
    r = forecast.summarize(day([slot(h) for h in range(0, 24, 3)]))
    assert "Опадів не видно." in r["text"]
    assert r["severity"] == "info"
    assert "Дощ" not in r["text"]


# TC3 — a response covering only the night names no part of the day it has no data for.
def test_night_only_response_does_not_invent_a_day():
    r = forecast.summarize(day([slot(0), slot(3)]))
    assert r["ok"]
    assert "Температура:" not in r["text"]
    for part in ("ранок", "день", "вечір"):
        assert part not in r["text"]


# TC4 — wind and cold raise the severity on their own.
def test_gust_and_cold_raise_severity():
    gusty = forecast.summarize(day([slot(h, windspeedKmph=40, WindGustKmph=70) for h in range(6, 24, 3)]))
    assert gusty["severity"] == "warn"
    assert "пориви до 70" in gusty["text"]

    frozen = forecast.summarize(day([slot(h, tempC=-14, FeelsLikeC=-20) for h in range(6, 24, 3)]))
    assert frozen["severity"] == "warn"
    assert "-14" in frozen["text"]


# The extras: frost before noon, thunder, fog — each only when the chance is real.
def test_extras_appear_only_when_likely():
    slots = [slot(h, chanceoffrost=70 if h <= 9 else 0, chanceofthunder=40 if h == 15 else 0)
             for h in range(0, 24, 3)]
    text = forecast.summarize(day(slots))["text"]
    assert "Уранці приморозок." in text
    assert "Можлива гроза." in text
    assert "Туман." not in text


# A broken payload must not raise: the probe contract is a record, never an exception.
def test_missing_astronomy_is_survivable():
    data = day([slot(h) for h in range(6, 24, 3)])
    del data["weather"][0]["astronomy"]
    r = forecast.summarize(data)
    assert r["ok"] and "Світає" not in r["text"]
