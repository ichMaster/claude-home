"""t1060 — the Moon's aspects have to be found across the whole day.

Fixed dates against the real ephemeris: `pyswisseph`'s Moshier model is offline and
deterministic, so these are regression tests, not approximations.
"""
from datetime import date

import astro          # status/ is on sys.path via conftest, and nothing shadows this name

DAY = date(2026, 10, 31)


def find(events, body, kind):
    return [e for e in events if e["other"] == body and e["kind"] == kind]


def test_evening_moon_square_venus_is_found():
    """The reference's ☽27°♋☐♀27°♎ from 20:29 — invisible to a noon snapshot, because at
    noon the Moon is 7° away from the square and outside the orb."""
    events = astro.moon_events(DAY)
    hit = find(events, "Венера", "квадратура")
    assert hit, "the evening square to Venus must exist as a fact"
    assert hit[0]["hour"] >= 18, f"expected an evening exactness, got {hit[0]['hour']}"


def test_noon_aspect_still_found():
    """What the old snapshot did catch must not be lost: the Moon–Mercury trine."""
    assert find(astro.moon_events(DAY), "Меркурій", "тригон")


def test_every_event_is_dated_and_bounded_by_the_day():
    for e in astro.moon_events(DAY):
        assert 0 <= e["hour"] <= 23
        assert e["exact"].startswith(DAY.isoformat())
        assert 0 < e["hours"] <= 24, "a Moon aspect cannot last longer than the day"


def test_natal_targets_are_covered_too():
    """A Moon transit to the natal chart is a trigger like any other."""
    events = astro.moon_events(DAY)
    assert any(e["natal"] for e in events), "natal targets must be scanned as well"
    assert any(not e["natal"] for e in events), "and sky targets too"


def test_one_entry_per_pairing():
    """Sampling every two hours must not yield one row per step."""
    events = astro.moon_events(DAY)
    keys = [(e["other"], e["kind"], e["natal"]) for e in events]
    assert len(keys) == len(set(keys))


def test_events_reach_the_fact_list():
    """The facts handed to the pipeline must carry the evening square, with its time."""
    texts = [f["text"] for f in astro.facts(DAY) if f.get("layer") == "moon"]
    joined = "\n".join(texts)
    assert "Венера" in joined and "квадратура" in joined
    assert any("близько" in t for t in texts), "the hour has to be in the text"


def test_exactness_outside_the_day_is_not_printed_as_midnight():
    """The scan's edge is not the passage's edge — the trap window_line() fell into once.
    A tightest point pinned to the day's first or last minutes with a wide orb means the
    real exactness is outside the day, and the line has to say so."""
    events = astro.moon_events(DAY)
    for e in events:
        line = astro.moon_event_line(e)
        assert "+0" not in line and "+1" not in line, f"timezone offset leaked: {line}"
        if e.get("edge"):
            assert "точно близько" not in line
            assert "доби" in line or "північ" in line
        else:
            assert "точно близько" in line


def test_venus_square_is_reported_as_running_past_midnight():
    """2026-10-31: the square tightens all evening and is exact after midnight, so the
    day's tightest moment is 23:50 — that must read as "past midnight", not as the peak."""
    hit = find(astro.moon_events(DAY), "Венера", "квадратура")[0]
    line = astro.moon_event_line(hit)
    assert hit["hour"] >= 18
    assert "23:50" in line or "північ" in line
