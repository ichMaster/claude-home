#!/usr/bin/env python
"""Astrology, computed here — the natal chart, the day's sky, the transits, the biorhythms.

Swiss Ephemeris via `pyswisseph` with the built-in Moshier model (`FLG_MOSEPH`), so no
ephemeris data files are needed; the positions agree with the full ephemeris to about
0.01°, the accuracy Кіра's chart in matrix-agora was verified against. Houses: Placidus.
The zodiac is tropical — astrology's signs, not the astronomical constellations.

Why computed and not asked of a model: matrix-agora learned the hard way that a model
invents transits. `agents/sky.py` there pays Gemini with Google Search for the day's
positions; here the same numbers come out of the ephemeris — free, offline, identical
every run. The model is left with the only job it is good at: reading the chart.

Pure: no network, no state, no clock of its own (the caller passes the day), so every
function is testable on a fixed date. Birth data lives in `config.local.json`
(`astro.birth`), never in the committed config.

CLI:
    astro.py --natal                 the natal chart: positions, houses, aspects
    astro.py --day 2026-10-27        that day's sky, its transits to the natal chart
    astro.py                         today (local), everything the mood call needs
    astro.py --json                  the same as JSON instead of Ukrainian lines
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf  # noqa: E402

SIGNS = ("Овен", "Телець", "Близнюки", "Рак", "Лев", "Діва",
         "Терези", "Скорпіон", "Стрілець", "Козоріг", "Водолій", "Риби")
# Genitive, for lines like "Місяць у Стрільці" — the dative/locative form the reading reads better with.
SIGNS_LOC = ("Овні", "Тельці", "Близнюках", "Раку", "Леві", "Діві",
             "Терезах", "Скорпіоні", "Стрільці", "Козерозі", "Водолії", "Рибах")
ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")

# The ten classical bodies, in the order a chart is read.
BODIES: tuple[tuple[str, int], ...] = (
    ("Сонце", swe.SUN), ("Місяць", swe.MOON), ("Меркурій", swe.MERCURY), ("Венера", swe.VENUS),
    ("Марс", swe.MARS), ("Юпітер", swe.JUPITER), ("Сатурн", swe.SATURN), ("Уран", swe.URANUS),
    ("Нептун", swe.NEPTUNE), ("Плутон", swe.PLUTO),
)
# Aspect name → exact angle. Orbs come from config (`astro.orbs`).
ASPECTS: tuple[tuple[str, float], ...] = (
    ("з'єднання", 0.0), ("секстиль", 60.0), ("квадратура", 90.0), ("тригон", 120.0), ("опозиція", 180.0),
)
FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED

# Sign → (traditional ruler, modern ruler). The modern one is None where the two agree.
# The reading is free to use either; what matters is that it uses the computed position of
# whichever it names, instead of guessing which planet "runs" a house.
RULERS: dict[str, tuple[str, str | None]] = {
    "Овен": ("Марс", None), "Телець": ("Венера", None), "Близнюки": ("Меркурій", None),
    "Рак": ("Місяць", None), "Лев": ("Сонце", None), "Діва": ("Меркурій", None),
    "Терези": ("Венера", None), "Скорпіон": ("Марс", "Плутон"), "Стрілець": ("Юпітер", None),
    "Козоріг": ("Сатурн", None), "Водолій": ("Сатурн", "Уран"), "Риби": ("Юпітер", "Нептун"),
}

# «натальне Сонце», «натальний Меркурій», «натальна Венера» — the adjective has to agree,
# and the reading quotes these lines verbatim.
NATAL_ADJ: dict[str, str] = {
    "Сонце": "натальне", "Місяць": "натальний", "Меркурій": "натальний", "Венера": "натальна",
    "Марс": "натальний", "Юпітер": "натальний", "Сатурн": "натальний", "Уран": "натальний",
    "Нептун": "натальний", "Плутон": "натальний", "ASC": "натальний", "MC": "натальний",
}

# What each body is *about* — the function, in the words the reading uses. Reference data,
# not interpretation invented per run: the same planet must mean the same thing every day.
PLANET_ROLE: dict[str, str] = {
    "Сонце": "увага, роль, те, чим день освітлений",
    "Місяць": "настрій, добовий фон, потреба",
    "Меркурій": "думка, слово, обмін",
    "Венера": "притягання, смак до життя, цінність",
    "Марс": "воля, натиск, дія",
    "Юпітер": "розширення, щедрість, перебільшення",
    "Сатурн": "межа, обов'язок, структура",
    "Уран": "злам, раптовість, свобода",
    "Нептун": "розмитість, образ, ілюзія",
    "Плутон": "тиск, трансформація, влада",
}
# What each house is about, in two to four words. Reference data, so the gloss next to
# «восьмий дім» is the same every morning instead of being improvised per run.
HOUSE_MEANING: dict[int, str] = {
    1: "ти сам, тіло, те, як заходиш у день",
    2: "свої гроші, речі, власний ресурс",
    3: "побутові розмови, ближнє коло, короткі поїздки",
    4: "дім, рід, коріння",
    5: "творчість, діти, гра, риск",
    6: "щоденна робота, режим, здоров'я",
    7: "партнерство, інші люди, домовленості",
    8: "спільні ресурси, борги, глибина, трансформація",
    9: "світогляд, велике знання, те, що кажеш на людях",
    10: "справа, покликання, як тебе бачать",
    11: "друзі, задуми, далекі плани",
    12: "те, що сховане, втома, тиша",
}

# Classical dignities: where a body is at home, exalted, in detriment, in fall. The modern
# three have no agreed exaltation, so they simply have none here.
DOMICILE: dict[str, tuple[str, ...]] = {
    "Сонце": ("Лев",), "Місяць": ("Рак",), "Меркурій": ("Близнюки", "Діва"),
    "Венера": ("Телець", "Терези"), "Марс": ("Овен", "Скорпіон"),
    "Юпітер": ("Стрілець", "Риби"), "Сатурн": ("Козоріг", "Водолій"),
    "Уран": ("Водолій",), "Нептун": ("Риби",), "Плутон": ("Скорпіон",),
}
EXALTATION: dict[str, str] = {
    "Сонце": "Овен", "Місяць": "Телець", "Меркурій": "Діва", "Венера": "Риби",
    "Марс": "Козоріг", "Юпітер": "Рак", "Сатурн": "Терези",
}
_OPPOSITE = {s: SIGNS[(i + 6) % 12] for i, s in enumerate(SIGNS)}

PERIODS: dict[str, int] = {"physical": 23, "emotional": 28, "intellectual": 33}
_BIO_UA = {"physical": "фізичний", "emotional": "емоційний", "intellectual": "інтелектуальний"}
_BIO_LABEL_UA = {"high": "високий", "low": "низький", "rising": "росте",
                 "falling": "спадає", "critical": "критичний"}


# --- the chart -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Position:
    """One body on the ecliptic: its longitude, the sign it falls in, the house, and whether it is retrograde."""

    name: str
    lon: float          # ecliptic longitude, 0–360
    sign: str
    deg: float          # degrees within the sign, 0–30
    house: int | None   # 1–12, or None when no houses were computed (a day's sky has no birthplace)
    retro: bool

    def line(self) -> str:
        """`Сонце — Скорпіон 19° (IX)`, with `℞` for a retrograde body."""
        house = f" ({ROMAN[self.house - 1]})" if self.house else ""
        retro = " ℞" if self.retro else ""
        return f"{self.name} — {self.sign} {int(self.deg)}°{house}{retro}"


@dataclass(frozen=True)
class Aspect:
    """An angle between two points, within orb."""

    a: str
    kind: str
    b: str
    orb: float          # how far from exact, in degrees

    def line(self) -> str:
        return f"{self.a} {self.kind} {self.b} ({self.orb:.1f}°)"


def _norm(deg: float) -> float:
    return deg % 360.0


def sign_of(lon: float) -> tuple[str, float]:
    """Longitude → (sign, degrees within that sign)."""
    lon = _norm(lon)
    return SIGNS[int(lon // 30)], lon % 30


def sign_loc(lon: float) -> str:
    """Longitude → the sign in the locative ("у Стрільці")."""
    return SIGNS_LOC[int(_norm(lon) // 30)]


def house_of(lon: float, cusps: tuple[float, ...] | None) -> int | None:
    """Which house a longitude falls in, given the twelve Placidus cusps."""
    if not cusps:
        return None
    lon = _norm(lon)
    for i in range(12):
        start, end = _norm(cusps[i]), _norm(cusps[(i + 1) % 12])
        span = _norm(end - start)
        if _norm(lon - start) < span:
            return i + 1
    return None


def julday(moment: datetime) -> float:
    """An aware datetime → the Julian day in UT, which is what the ephemeris wants."""
    utc = moment.astimezone(ZoneInfo("UTC"))
    return swe.julday(utc.year, utc.month, utc.day,
                      utc.hour + utc.minute / 60 + utc.second / 3600)


def positions(moment: datetime, lat: float | None = None, lon: float | None = None,
              hsys: str | None = None) -> tuple[list[Position], dict[str, float]]:
    """The ten bodies at `moment`, plus the angles when a place is given.

    Returns (positions, angles); `angles` holds ASC and MC (and the cusps under `cusps`)
    only if lat/lon were passed — a day's sky has no birthplace, so it has no houses.
    """
    jd = julday(moment)
    cusps: tuple[float, ...] | None = None
    angles: dict[str, float] = {}
    if lat is not None and lon is not None:
        hs = (hsys or conf("astro.houses", "P")).encode()
        cusps, ascmc = swe.houses_ex(jd, lat, lon, hs)
        angles = {"asc": ascmc[0], "mc": ascmc[1], "cusps": list(cusps)}

    out: list[Position] = []
    for name, ipl in BODIES:
        xx, _ = swe.calc_ut(jd, ipl, FLAGS)
        sign, deg = sign_of(xx[0])
        out.append(Position(name, _norm(xx[0]), sign, deg, house_of(xx[0], cusps), xx[3] < 0))
    return out, angles


def aspects(points: dict[str, float], other: dict[str, float] | None = None) -> list[Aspect]:
    """Aspects within one set of points, or between two sets (transits to a natal chart).

    Orbs are per aspect from `astro.orbs`; the tighter the orb, the fewer and the more
    meaningful the hits. Sorted by how exact they are.
    """
    orbs = conf("astro.orbs", {})
    default_orb = conf("astro.orb", 5.0)
    found: list[Aspect] = []
    pairs = ([(a, b) for i, a in enumerate(points) for b in list(points)[i + 1:]] if other is None
             else [(a, b) for a in points for b in other])
    right = other if other is not None else points
    for a, b in pairs:
        delta = abs(_norm(points[a] - right[b]))
        delta = min(delta, 360 - delta)
        for kind, exact in ASPECTS:
            orb = float(orbs.get(kind, default_orb))
            if abs(delta - exact) <= orb:
                found.append(Aspect(a, kind, b, abs(delta - exact)))
                break
    return sorted(found, key=lambda x: x.orb)


def moon_phase(sun_lon: float, moon_lon: float) -> tuple[str, float]:
    """(phase in words, illuminated fraction 0–1) from the Moon's elongation from the Sun."""
    elong = _norm(moon_lon - sun_lon)
    illum = (1 - math.cos(math.radians(elong))) / 2
    if elong < 15 or elong >= 345:
        name = "молодик"
    elif elong < 75:
        name = "молодий серп, росте"
    elif elong < 105:
        name = "перша чверть"
    elif elong < 165:
        name = "росте, майже повня"
    elif elong < 195:
        name = "повня"
    elif elong < 255:
        name = "спадає після повні"
    elif elong < 285:
        name = "остання чверть"
    else:
        name = "спадний серп, перед молодиком"
    return name, illum


# --- biorhythms ----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Cycle:
    """One biorhythm cycle: its value in −1…+1 and a phase label."""

    name: str
    value: float
    label: str          # high | low | rising | falling | critical


def _bio_label(value: float, value_next: float) -> str:
    """`critical` at or around a zero crossing, else high / low / rising / falling."""
    if value == 0.0 or (value > 0) != (value_next > 0):
        return "critical"
    if value >= 0.7:
        return "high"
    if value <= -0.7:
        return "low"
    return "rising" if value_next > value else "falling"


def biorhythms(birth: date, today: date) -> list[Cycle]:
    """The three classic sine cycles for `today` — exact, deterministic, no model involved.

    Ported from lumi `core/biorhythm.py` (MIT), the same math matrix-agora uses, so the
    numbers here and Кіра's agree for the same birth date.
    """
    d = (today - birth).days
    out: list[Cycle] = []
    for name, period in PERIODS.items():
        value = math.sin(2 * math.pi * d / period)
        value_next = math.sin(2 * math.pi * (d + 1) / period)
        out.append(Cycle(name, value, _bio_label(value, value_next)))
    return out


def format_biorhythms(cycles: list[Cycle]) -> str:
    """`фізичний +0.82 (високий) · емоційний −0.61 (низький) · інтелектуальний +0.10 (росте)`."""
    return " · ".join(f"{_BIO_UA[c.name]} {c.value:+.2f} ({_BIO_LABEL_UA[c.label]})" for c in cycles)


# --- the birth data ------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Birth:
    """The fixed birth moment and place, from `config.local.json` (`astro.birth`)."""

    date: date
    moment: datetime    # aware, in the birth timezone
    place: str
    lat: float
    lon: float

    @property
    def utc(self) -> datetime:
        return self.moment.astimezone(ZoneInfo("UTC"))


# Whose chart is being read. `None` is the owner (`astro.birth`); a name selects
# `astro.subjects.<name>`, which is how a chart other than his own gets computed without
# duplicating the whole module. Set once by the CLI or by `mood.py --subject`.
SUBJECT: str | None = None


def subject_conf(key: str, default=None):
    """A per-subject setting, falling back to the owner's own."""
    if SUBJECT:
        value = conf(f"astro.subjects.{SUBJECT}.{key}")
        if value is not None:
            return value
    return conf(f"astro.{key}", default)


def birth_data() -> Birth:
    """Read the birth data out of the config. Raises if it is not configured — there is no
    sane default for someone's birth moment, and a guessed one would quietly produce a
    wrong chart."""
    b = subject_conf("birth") or {}
    missing = [k for k in ("date", "time", "tz", "lat", "lon") if not b.get(k)]
    if missing:
        who = f"astro.subjects.{SUBJECT}.birth" if SUBJECT else "astro.birth"
        raise SystemExit(f"{who} у config.local.json не заповнено: {', '.join(missing)}")
    d = date.fromisoformat(b["date"])
    hh, mm = (int(x) for x in str(b["time"]).split(":")[:2])
    moment = datetime.combine(d, time(hh, mm), ZoneInfo(b["tz"]))
    return Birth(d, moment, b.get("place", ""), float(b["lat"]), float(b["lon"]))


# --- the two readings the mood call needs --------------------------------------------------------------------------

def houses_table(cusps: list[float], where: dict[str, Position]) -> list[dict]:
    """The twelve houses: the cusp, the sign on it, its ruler, and where that ruler stands.

    A transit through a house says which part of life is being touched; the ruler says
    through whom or what. Both are plain lookups once the cusps are known, so neither has
    to be guessed by the model.
    """
    out = []
    for i, cusp in enumerate(cusps):
        sign, deg = sign_of(cusp)
        trad, modern = RULERS[sign]
        row = {"house": i + 1, "sign": sign, "deg": deg, "ruler": trad, "modern": modern}
        for key, planet in (("ruler_at", trad), ("modern_at", modern)):
            p = where.get(planet) if planet else None
            row[key] = f"{p.sign} {int(p.deg)}° ({ROMAN[p.house - 1]})" if p and p.house else None
        out.append(row)
    return out


def natal_chart() -> dict:
    """The natal chart: every body with its sign, degree and house, the angles, the aspects.

    A fixed snapshot — it never changes — so the caller may cache it in a file and the
    numbers will still match a fresh run.
    """
    b = birth_data()
    pos, angles = positions(b.moment, b.lat, b.lon)
    by_name = {p.name: p.lon for p in pos}
    asc, mc = angles["asc"], angles["mc"]
    phase, illum = moon_phase(by_name["Сонце"], by_name["Місяць"])
    return {
        "birth": {"date": b.date.isoformat(), "time": b.moment.strftime("%H:%M"),
                  "tz": str(b.moment.tzinfo), "utc": b.utc.strftime("%Y-%m-%d %H:%M"),
                  "place": b.place, "lat": b.lat, "lon": b.lon},
        "positions": [asdict(p) for p in pos],
        "asc": {"lon": asc, "sign": sign_of(asc)[0], "deg": sign_of(asc)[1]},
        "mc": {"lon": mc, "sign": sign_of(mc)[0], "deg": sign_of(mc)[1]},
        "cusps": angles["cusps"],
        "houses": houses_table(angles["cusps"], {p.name: p for p in pos}),
        "aspects": [asdict(a) for a in aspects({**by_name, "ASC": asc, "MC": mc})],
        "moon": {"phase": phase, "illuminated": round(illum, 3)},
    }


def day_sky(day: date) -> dict:
    """That day's sky, read at local noon (the Moon moves 13° a day, so noon is the fair
    midpoint), plus the transits to the natal chart and the biorhythms."""
    tz = ZoneInfo(conf("astro.tz", "Europe/Kyiv"))
    noon = datetime.combine(day, time(12, 0), tz)
    pos, _ = positions(noon)
    by_name = {p.name: p.lon for p in pos}
    phase, illum = moon_phase(by_name["Сонце"], by_name["Місяць"])

    b = birth_data()
    npos, nangles = positions(b.moment, b.lat, b.lon)
    natal_points = {p.name: p.lon for p in npos}
    natal_points.update({"ASC": nangles["asc"], "MC": nangles["mc"]})
    # Transits name the moving body first: "транзитний Марс квадратура натальне Сонце".
    to_natal = aspects(by_name, natal_points)

    # Each moving body also stands in one of HIS natal houses today — the aspect says what
    # is being touched, the house says where in a life it happens. The day's own sky has no
    # houses of its own (no birthplace), so they come from the natal cusps.
    cusps = nangles["cusps"]
    pos = [Position(p.name, p.lon, p.sign, p.deg, house_of(p.lon, cusps), p.retro) for p in pos]

    return {
        "day": day.isoformat(),
        "positions": [asdict(p) for p in pos],
        "retrograde": [p.name for p in pos if p.retro],
        "moon": {"phase": phase, "illuminated": round(illum, 3)},
        "aspects": [asdict(a) for a in aspects(by_name)],
        "transits": [asdict(a) for a in to_natal],
        "biorhythms": [asdict(c) for c in biorhythms(b.date, day)],
    }


# --- how long a transit lasts, and whether today is its peak -------------------------------------------------------
#
# A transit's weight is not its orb today. Transiting Moon opposite the natal Sun is exact
# for an afternoon; transiting Saturn trine the natal MC is exact for a fortnight and in
# orb for two months. The owner (2026-10-27) asked for exactly this: weigh the day's facts
# "from the position of the whole month or quarter". That weight is computable, so it is
# computed here rather than guessed by the model.

def _aspect_orb(kind: str) -> float:
    return float(conf("astro.orbs", {}).get(kind, conf("astro.orb", 5.0)))


def _separation(moving_lon: float, fixed_lon: float, exact_angle: float) -> float:
    """How far from exact this aspect is, in degrees."""
    delta = abs(_norm(moving_lon - fixed_lon))
    delta = min(delta, 360 - delta)
    return abs(delta - exact_angle)


def transit_window(body: str, natal_lon: float, kind: str, day: date,
                   span: int | None = None) -> dict:
    """When this transit came into orb, when it is exact, when it leaves — around `day`.

    Walks the ephemeris day by day over ±`span` days (config `astro.window_days`) and
    reports the stretch containing `day`. Cheap: one `calc_ut` per day per body.

    `trend` is what the day feels like — `сходиться` (building), `точно` (peak within a
    day), `розходиться` (separating). `days` is how long the whole passage lasts, which is
    the number that separates a Moon trigger from a Saturn season.
    """
    span = span or conf("astro.window_days", 45)
    ipl = dict(BODIES)[body]
    exact_angle = dict(ASPECTS)[kind]
    orb_limit = _aspect_orb(kind)
    tz = ZoneInfo(conf("astro.tz", "Europe/Kyiv"))

    orbs: dict[int, float] = {}
    for offset in range(-span, span + 1):
        jd = julday(datetime.combine(day + timedelta(days=offset), time(12, 0), tz))
        xx, _ = swe.calc_ut(jd, ipl, FLAGS)
        orbs[offset] = _separation(xx[0], natal_lon, exact_angle)

    if orbs[0] > orb_limit:                       # not actually in orb today
        return {"in_orb": False}

    start = end = 0
    while start - 1 >= -span and orbs[start - 1] <= orb_limit:
        start -= 1
    while end + 1 <= span and orbs[end + 1] <= orb_limit:
        end += 1
    peak = min(range(start, end + 1), key=lambda o: orbs[o])

    trend = "точно" if abs(peak) <= 1 else ("сходиться" if peak > 0 else "розходиться")
    return {
        "in_orb": True,
        "from": (day + timedelta(days=start)).isoformat(),
        "to": (day + timedelta(days=end)).isoformat(),
        "exact": (day + timedelta(days=peak)).isoformat(),
        "days": end - start + 1,
        "open_before": start <= -span,            # the passage began before the window
        "open_after": end >= span,                # and/or runs past it
        "trend": trend,
        "orb_today": round(orbs[0], 2),
    }


def window_line(w: dict) -> str:
    """The window in words, careful not to pass a scan limit off as a transit's edge.

    `transit_window` only looks ±`astro.window_days`, so a slow passage usually runs past
    both ends of that look. Printing those ends as the start and finish of the transit made
    the reading state them as fact — the review pass caught it (2026-10-27). An open end is
    now named as open, and an exactness that falls on the scan edge is reported as "not
    before" rather than as a date.
    """
    if not w.get("in_orb"):
        return ""
    open_before, open_after = w.get("open_before"), w.get("open_after")
    span = f"тримається {w['days']} дн" + ("+" if open_before or open_after else "")
    bounds = ("почалось до " + w["from"] if open_before else "з " + w["from"])
    bounds += (", щонайменше до " + w["to"] if open_after else ", до " + w["to"])

    if w["trend"] == "точно":
        when = "точно зараз"
    elif open_after and w["trend"] == "сходиться":
        when = f"точність не раніше {w['exact']}"
    elif open_before and w["trend"] == "розходиться":
        when = f"точність була не пізніше {w['exact']}"
    else:
        when = f"точно {w['exact']}" if w["trend"] == "сходиться" else f"точно було {w['exact']}"
    return f"{span} ({bounds}), {when}, орбіс {w['orb_today']}°"


def day_focus(day: date) -> dict:
    """Which body is loudest today and which house is the day's arena — computed, not felt.

    The owner's model of a summary (2026-10-27) opens with exactly this: "the Sun sets the
    tone today, the 8th house is the main arena". Both are countable, so they are counted
    here instead of being left to a model's impression: every transit to a natal point
    scores `1/(orb + 0.5)` — the tighter, the louder — and the score goes to the moving body
    and to the house its natal target sits in. A body merely standing in a house adds half a
    point to that house, since presence is weaker than contact.
    """
    sky = day_sky(day)
    b = birth_data()
    npos, nangles = positions(b.moment, b.lat, b.lon)
    natal_house = {p.name: p.house for p in npos}
    natal_house.update({"ASC": 1, "MC": 10})

    bodies: dict[str, float] = {}
    houses: dict[int, float] = {}
    for a in sky["transits"]:
        weight = 1.0 / (a["orb"] + 0.5)
        bodies[a["a"]] = bodies.get(a["a"], 0.0) + weight
        house = natal_house.get(a["b"])
        if house:
            houses[house] = houses.get(house, 0.0) + weight
    for p in sky["positions"]:
        if p["house"]:
            houses[p["house"]] = houses.get(p["house"], 0.0) + 0.5

    rank_b = sorted(bodies.items(), key=lambda kv: -kv[1])
    rank_h = sorted(houses.items(), key=lambda kv: -kv[1])
    return {
        "bodies": [{"name": n, "score": round(v, 2)} for n, v in rank_b],
        "houses": [{"house": h, "score": round(v, 2)} for h, v in rank_h],
        "loudest": rank_b[0][0] if rank_b else None,
        "arena": rank_h[0][0] if rank_h else None,
    }


def dignity(body: str, sign: str) -> str:
    """`у своєму знаку` / `в екзальтації` / `у вигнанні` / `у падінні` / `нейтрально`."""
    if sign in DOMICILE.get(body, ()):
        return "у своєму знаку"
    if sign == EXALTATION.get(body):
        return "в екзальтації"
    if any(sign == _OPPOSITE[s] for s in DOMICILE.get(body, ())):
        return "у вигнанні"
    if body in EXALTATION and sign == _OPPOSITE[EXALTATION[body]]:
        return "у падінні"
    return "нейтрально за знаком"


def body_state(day: date, name: str) -> str:
    """One body's standing today: role, sign and dignity, the natal house it crosses,
    retrogradation, and the balance of its aspects — support against friction.

    All of it computed. The owner's model of an explanation (2026-10-27) names the planet's
    function, where it sits, what condition it is in and who presses on it; none of that
    should be a model's impression when it can be read off the ephemeris.
    """
    sky = day_sky(day)
    pos = next((p for p in sky["positions"] if p["name"] == name), None)
    if not pos:
        return ""
    soft = [a for a in sky["aspects"] if a["kind"] in ("тригон", "секстиль")
            and name in (a["a"], a["b"])]
    hard = [a for a in sky["aspects"] if a["kind"] in ("квадратура", "опозиція")
            and name in (a["a"], a["b"])]
    join = [a for a in sky["aspects"] if a["kind"] == "з'єднання" and name in (a["a"], a["b"])]

    def other(a):
        return a["b"] if a["a"] == name else a["a"]

    bits = [f"{name} — {PLANET_ROLE.get(name, '')}",
            f"у {sign_loc(pos['lon'])} ({dignity(name, pos['sign'])})"]
    if pos["house"]:
        bits.append(f"проходить твій {ROMAN[pos['house'] - 1]} дім")
    if pos["retro"]:
        bits.append("ретроградний")
    if join:
        bits.append("у з'єднанні з " + ", ".join(other(a) for a in join))
    bits.append("підтримка: " + (", ".join(f"{a['kind']} до {other(a)}" for a in soft) or "немає"))
    bits.append("тертя: " + (", ".join(f"{a['kind']} до {other(a)}" for a in hard) or "немає"))
    # what it is doing to the natal chart, which is where it actually lands
    to_natal = [a for a in sky["transits"] if a["a"] == name]
    if to_natal:
        bits.append("до натальної карти: " +
                    "; ".join(f"{a['kind']} до {NATAL_ADJ.get(a['b'], 'натальний')} {a['b']}"
                              for a in to_natal[:4]))
    return "; ".join(b for b in bits if b)


def focus_lines(focus: dict, day: date | None = None) -> str:
    """The focus in words: the loudest bodies, the leading houses, and — when a day is
    given — the full standing of the two loudest bodies."""
    bodies = ", ".join(f"{b['name']} ({b['score']})" for b in focus["bodies"][:4])
    houses = ", ".join(f"{ROMAN[h['house'] - 1]} ({h['score']})" for h in focus["houses"][:4])
    head = ""
    if focus["loudest"] and focus["arena"]:
        head = (f"Найактивніша планета дня: {focus['loudest']}. "
                f"Головна арена: {ROMAN[focus['arena'] - 1]} дім.\n")
    out = f"{head}Активність планет: {bodies}.\nЗавантаженість домів: {houses}."
    if day:
        states = [body_state(day, b["name"]) for b in focus["bodies"][:2]]
        out += "\nСтан головних планет:\n" + "\n".join(f"- {x}" for x in states if x)
    return out


def glossary_lines() -> str:
    """The short glosses the reading quotes in brackets: each house and each body in a few
    words. Fixed text, so «восьмий дім (спільні ресурси, борги)» reads the same every day."""
    houses = "; ".join(f"{ROMAN[h - 1]} дім — {m}" for h, m in HOUSE_MEANING.items())
    bodies = "; ".join(f"{n} — {r}" for n, r in PLANET_ROLE.items())
    return f"Доми: {houses}.\nПланети: {bodies}."


def natal_moon_lines() -> str:
    """The natal Moon in one line, with the aspects it makes — the Moon layer needs to know
    what the day's Moon is landing on."""
    chart = natal_chart()
    moon = next((p for p in chart["positions"] if p["name"] == "Місяць"), None)
    if not moon:
        return ""
    asp = "; ".join(Aspect(**a).line() for a in chart["aspects"]
                    if "Місяць" in (a["a"], a["b"]))
    where = f"{moon['sign']} {int(moon['deg'])}°"
    house = f", {ROMAN[moon['house'] - 1]} дім" if moon["house"] else ""
    return f"натальний Місяць — {where}{house}; його аспекти: {asp or 'немає тісних'}"


def facts(day: date) -> list[dict]:
    """The day as a list of separate, weighable facts — the input to the per-fact reading.

    Each fact is one configuration: a transit to a natal point, a transiting body standing
    in a natal house, the retrograde set, the Moon's phase, or a tight aspect in the sky
    itself. Transits carry their window, so a later pass can tell a two-hour trigger from a
    two-month season.
    """
    sky = day_sky(day)
    b = birth_data()
    npos, nangles = positions(b.moment, b.lat, b.lon)
    natal_lon = {p.name: p.lon for p in npos}
    natal_lon.update({"ASC": nangles["asc"], "MC": nangles["mc"]})
    natal_house = {p.name: p.house for p in npos}
    houses = {h["house"]: h for h in houses_table(nangles["cusps"], {p.name: p for p in npos})}

    out: list[dict] = []
    limits = conf("astro.facts", {})
    for a in sky["transits"][:int(limits.get("transits", 10))]:
        w = transit_window(a["a"], natal_lon[a["b"]], a["kind"], day)
        target = f"{NATAL_ADJ.get(a['b'], 'натальний')} {a['b']}"
        house = natal_house.get(a["b"])
        where = (f" ({NATAL_ADJ.get(a['b'], 'натальний')} {a['b']} "
                 f"у твоєму {ROMAN[house - 1]} домі)") if house else ""
        out.append({
            "id": f"t{len(out) + 1}",
            "kind": "transit",
            "layer": "moon" if a["a"] == "Місяць" else "transit",
            "text": f"транзитний {a['a']} {a['kind']} {target} ({a['orb']:.1f}°){where}",
            "orb": a["orb"],
            "window": w,
            "window_text": window_line(w),
        })

    for p in sky["positions"]:
        if not p["house"]:
            continue
        h = houses.get(p["house"], {})
        ruler = f", господар дому {h.get('ruler')}" if h.get("ruler") else ""
        out.append({
            "id": f"h{p['house']}-{p['name']}",
            "kind": "house",
            "layer": "moon" if p["name"] == "Місяць" else "house",
            "text": (f"транзитний {p['name']} у {p['sign']} проходить твій {ROMAN[p['house'] - 1]} дім"
                     f"{' ретроградно' if p['retro'] else ''}{ruler}"),
            "orb": None, "window": {}, "window_text": "",
        })

    if sky["retrograde"]:
        out.append({"id": "retro", "kind": "retro", "layer": "background",
                    "text": "ретроградні сьогодні: " + ", ".join(sky["retrograde"]),
                    "orb": None, "window": {}, "window_text": ""})

    out.append({"id": "moon", "kind": "moon", "layer": "moon",
                "text": (f"Місяць — {sky['moon']['phase']}, освітлення "
                         f"{sky['moon']['illuminated']:.0%}"),
                "orb": None, "window": {}, "window_text": ""})

    for a in sky["aspects"][:int(limits.get("sky", 4))]:
        out.append({"id": f"s{a['a']}-{a['b']}", "kind": "sky",
                    "layer": "moon" if "Місяць" in (a["a"], a["b"]) else "background",
                    "text": f"у небі самому: {a['a']} {a['kind']} {a['b']} ({a['orb']:.1f}°)",
                    "orb": a["orb"], "window": {}, "window_text": ""})
    return out


# --- Ukrainian rendering, which is what goes into the prompt -------------------------------------------------------

def natal_lines(chart: dict) -> str:
    """The natal chart as the few lines the mood prompt reads."""
    bi = chart["birth"]
    head = f"Народження: {bi['date']}, {bi['time']} ({bi['tz']}), {bi['place']}."
    pos = " · ".join(Position(**p).line() for p in chart["positions"])
    ang = (f"ASC {chart['asc']['sign']} {chart['asc']['deg']:.0f}° · "
           f"MC {chart['mc']['sign']} {chart['mc']['deg']:.0f}°")
    asp = "; ".join(Aspect(**a).line() for a in chart["aspects"][:12])
    houses = "; ".join(
        f"{ROMAN[h['house'] - 1]} — {h['sign']} {int(h['deg'])}°, керує {h['ruler']}"
        + (f"/{h['modern']}" if h["modern"] else "")
        + (f" (стоїть у {h['ruler_at']})" if h.get("ruler_at") else "")
        for h in chart.get("houses", []))
    return (f"{head}\n{pos} · {ang}.\n"
            f"Місяць: {chart['moon']['phase']} (освітлення {chart['moon']['illuminated']:.0%}).\n"
            f"Доми (Плацидус): {houses}.\n"
            f"Аспекти карти: {asp}.")


def sky_lines(sky: dict) -> str:
    """The day's sky, its transits and the biorhythms, as the prompt reads them."""
    pos = "; ".join(
        f"{Position(**p).name} — {p['sign']} {int(p['deg'])}°"
        + (f", твій {ROMAN[p['house'] - 1]} дім" if p["house"] else "")
        + (" ℞" if p["retro"] else "")
        for p in sky["positions"])
    retro = ", ".join(sky["retrograde"]) or "немає"
    asp = "; ".join(Aspect(**a).line() for a in sky["aspects"][:10]) or "немає тісних"
    tr = "; ".join(f"транзитний {a['a']} {a['kind']} натальне {a['b']} ({a['orb']:.1f}°)"
                   for a in sky["transits"][:12]) or "немає тісних"
    bio = format_biorhythms([Cycle(**c) for c in sky["biorhythms"]])
    return (f"Положення на {sky['day']}: {pos}.\n"
            f"Ретроградні: {retro}. Місяць: {sky['moon']['phase']} "
            f"(освітлення {sky['moon']['illuminated']:.0%}).\n"
            f"Аспекти дня: {asp}.\n"
            f"Транзити до натальної карти: {tr}.\n"
            f"Біоритми: {bio}.")


def main() -> int:
    ap = argparse.ArgumentParser(description="натальна карта, небо дня, транзити, біоритми")
    ap.add_argument("--natal", action="store_true", help="тільки натальна карта")
    ap.add_argument("--sky", action="store_true", help="тільки небо дня, транзити й біоритми")
    ap.add_argument("--day", help="дата у форматі YYYY-MM-DD (типово — сьогодні)")
    ap.add_argument("--json", action="store_true", help="JSON замість рядків")
    ap.add_argument("--subject", help="чия карта (astro.subjects.<name>); типово — власник")
    args = ap.parse_args()

    global SUBJECT
    SUBJECT = args.subject

    if args.natal:
        chart = natal_chart()
        print(json.dumps(chart, ensure_ascii=False, indent=2) if args.json else natal_lines(chart))
        return 0

    day = date.fromisoformat(args.day) if args.day else datetime.now(
        ZoneInfo(conf("astro.tz", "Europe/Kyiv"))).date()
    sky = day_sky(day)
    if args.json:
        print(json.dumps(sky if args.sky else {"natal": natal_chart(), "sky": sky},
                         ensure_ascii=False, indent=2))
    elif args.sky:
        print(sky_lines(sky))
    else:
        print(natal_lines(natal_chart()))
        print()
        print(sky_lines(sky))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
