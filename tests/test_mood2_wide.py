"""t1195 — his month and his year reach the day.

He publishes three horizons: an hourly calendar for the day, a month, and a year. Until now
only the day was read, so a Tuesday his own month calls one of its five events sounded like
any other Tuesday. The owner asked for both to be folded in (16 November): a concrete date
merges into that day's reading, a period is said at the end in his own style.

The division of labour is the standing one — the model reads his prose, arithmetic decides
what covers today. These tests are the arithmetic half, plus the shape of the reading.
"""
import json
from datetime import date

import pytest

import astro_learn
import mood2

DAY = date(2026, 11, 16)

# What a correct `wide` stage returns for a month and a year: one event dated today, one dated
# another day, one period holding over today, one that ended, one that has not begun, and one
# whose date cannot be read at all. Invented values — his texts never enter the repository.
ENTRIES = [
    {"scope": "місяць", "kind": "date", "from": "2026-11-16", "to": None, "weight": 4,
     "bodies": "Плутон", "meaning": "Велика задача, що вимагає самовіддачі.", "natal": None},
    {"scope": "місяць", "kind": "date", "from": "2026-11-20", "to": None, "weight": 4,
     "bodies": "Ліліт", "meaning": "Репутаційні ризики в професії.", "natal": None},
    {"scope": "місяць", "kind": "period", "from": "2026-11-01", "to": "2026-11-30",
     "weight": 3, "bodies": "Нептун", "meaning": "Мрії та натхнення.", "natal": None},
    {"scope": "рік", "kind": "period", "from": "2026-10-07", "to": "2026-11-12",
     "weight": 3, "bodies": "Венера", "meaning": "Давні бажання тягнуть назад.",
     "natal": None},
    {"scope": "рік", "kind": "period", "from": "2026-11-28", "to": "2026-12-19",
     "weight": 2, "bodies": "Уран", "meaning": "Прорив у технологіях.", "natal": None},
    {"scope": "рік", "kind": "period", "from": "коли вийде", "to": None, "weight": 5,
     "bodies": "Сатурн", "meaning": "Невідомо коли.", "natal": None},
]


# --- TC1: which reference covers a day -----------------------------------------------------

def test_covering_picks_the_month_and_the_year_of_that_day(monkeypatch):
    records = [
        {"day": "2026-11-01", "period": "місяць", "text": "листопад"},
        {"day": "2026-10-01", "period": "місяць", "text": "жовтень"},
        {"day": "2026-01-01", "period": "рік", "text": "2026"},
        {"day": "2025-01-01", "period": "рік", "text": "2025"},
        {"day": "2026-11-15", "period": "день", "text": "одна доба"},
    ]
    monkeypatch.setattr(astro_learn, "references", lambda day=None: records)
    assert astro_learn.covering(DAY) == {"місяць": "листопад", "рік": "2026"}
    assert astro_learn.covering(date(2026, 10, 5))["місяць"] == "жовтень"
    assert "місяць" not in astro_learn.covering(date(2026, 9, 5))
    assert astro_learn.covering(date(2025, 11, 5)) == {"рік": "2025"}


def test_covering_takes_the_latest_record_of_each_kind(monkeypatch):
    records = [
        {"day": "2026-11-01", "period": "місяць", "text": "перша версія"},
        {"day": "2026-11-01", "period": "місяць", "text": "виправлена"},
    ]
    monkeypatch.setattr(astro_learn, "references", lambda day=None: records)
    assert astro_learn.covering(DAY)["місяць"] == "виправлена"


# --- TC2, TC4: arithmetic decides what reaches the day --------------------------------------

def test_only_todays_date_and_a_holding_period_survive():
    out = mood2.wide_relevant(ENTRIES, DAY, cap=3)
    assert [e["bodies"] for e in out["day"]] == ["Плутон"]
    assert [e["bodies"] for e in out["period"]] == ["Нептун"]
    assert out["dropped"], "an unreadable date is reported, never guessed"


def test_a_period_is_capped_by_weight_and_the_rest_is_reported():
    many = [dict(ENTRIES[2], weight=w, bodies=f"Тіло{w}") for w in (1, 5, 3, 4, 2)]
    out = mood2.wide_relevant(many, DAY, cap=2)
    assert [e["bodies"] for e in out["period"]] == ["Тіло5", "Тіло4"]
    assert any("Тіло3" in d or "3" in d for d in out["dropped"]), out["dropped"]


def test_the_entries_get_ids_and_a_kind():
    out = mood2.wide_relevant(ENTRIES, DAY, cap=3)
    assert out["day"][0]["id"] == "w1" and out["day"][0]["kind"] == "wide"
    assert out["period"][0]["id"] == "w2" and out["period"][0]["kind"] == "period"


def test_a_wide_position_weighs_on_the_day():
    """TC3 — a dated monthly event is a position like any other."""
    out = mood2.wide_relevant(ENTRIES, DAY, cap=3)
    items = [{"id": "p1", "kind": "window", "from": "10:00", "to": "12:00", "weight": 1,
              "bodies": "Сатурн", "meaning": "Дрібниця.", "natal": None}] + out["day"]
    state = mood2.pressure(items)
    assert state["top"] == 4
    assert state["loud"] == ["w1"] and state["accent"] == ["w1"]
    assert "w1" in mood2.mandatory_ids(items)


# --- TC5, TC6: the ПЕРІОД part --------------------------------------------------------------

ITEMS = [{"id": "p1", "kind": "window", "from": "10:00", "to": "12:00", "weight": 3,
          "bodies": "Сатурн", "house": "7", "formula": "(☽9°♍△♄9°♉)",
          "meaning": "Тягне тиснути і доводити своє.", "natal": None, "span": None}]
WIDE = {"day": [], "period": [{"id": "w1", "kind": "period", "scope": "місяць",
                               "from": "2026-11-01", "to": "2026-11-30", "weight": 3,
                               "bodies": "Нептун", "meaning": "Мрії та натхнення.",
                               "natal": None}]}

READING = """ДЕНЬ
Доба одного вікна. [p1]

ПРОГНОЗ
зранку | Сатурн у домі себе — тягне тиснути й доводити своє [p1]

АКЦЕНТ
зранку | голосне в добі: впертість, що приймає себе за правоту [p1]

ДІЯ
Не плутай впертість із правотою. [p1]

ПЕРІОД
протягом усього листопада — Нептун тримає мрійливість і тягне до натхнення більше, ніж до справ [w1]

ОСНОВА
p1 10:00-12:00 ✤✤✤ (☽9°♍△♄9°♉) · w1 місяць Нептун
"""


def test_the_sections_are_six_and_the_period_is_last_spoken():
    assert mood2.SECTIONS == ("ДЕНЬ", "ПРОГНОЗ", "АКЦЕНТ", "ДІЯ", "ПЕРІОД", "ОСНОВА")
    assert mood2.check_reading(READING, ITEMS, None, WIDE) == []


def test_a_reading_without_the_period_part_is_caught():
    bad = READING.replace("ПЕРІОД", "ХТОЗНА")
    assert any("нема частини ПЕРІОД" in p
               for p in mood2.check_reading(bad, ITEMS, None, WIDE))


def test_a_period_that_was_never_said_is_caught():
    bad = READING.replace(
        "протягом усього листопада — Нептун тримає мрійливість і тягне до натхнення "
        "більше, ніж до справ [w1]", "нічого довгого зараз не тримається")
    problems = mood2.check_reading(bad, ITEMS, None, WIDE)
    assert any("ПЕРІОД" in p and "w1" in p for p in problems), problems


def test_a_figure_in_the_period_is_caught():
    bad = READING.replace("протягом усього листопада", "протягом з 1 до 30 листопада")
    problems = mood2.check_reading(bad, ITEMS, None, WIDE)
    assert any("цифр" in p for p in problems), problems


def test_a_day_with_no_period_still_has_the_part():
    """TC6 — the part stays, and says nothing is holding."""
    empty = {"day": [], "period": []}
    text = READING.replace(
        "протягом усього листопада — Нептун тримає мрійливість і тягне до натхнення "
        "більше, ніж до справ [w1]", "нічого довгого зараз не тримається")
    assert mood2.check_reading(text, ITEMS, None, empty) == []


def test_the_period_is_spoken_with_a_breath():
    said = mood2.voice_text(READING)
    assert "ПЕРІОД" not in said
    assert "протягом усього листопада" in said


# --- TC7: a body only the month carries -----------------------------------------------------

def test_a_body_of_the_month_may_be_named():
    assert not any("яких у добі немає" in p
                   for p in mood2.check_reading(READING, ITEMS, None, WIDE))


def test_a_body_of_the_month_that_never_sounds_is_reported():
    bad = READING.replace("Нептун тримає мрійливість і тягне", "щось тримає і тягне")
    problems = mood2.check_reading(bad, ITEMS, None, WIDE)
    assert any("яких у читанні немає" in p and "Нептун" in p for p in problems), problems


# --- TC8: one call a month, not thirty ------------------------------------------------------

def test_the_extraction_is_cached_by_the_text(monkeypatch, tmp_path):
    calls = []

    def fake_call(stage, prompt):
        calls.append(stage)
        return json.dumps(ENTRIES, ensure_ascii=False)

    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"v2-{key}")
    monkeypatch.setattr(astro_learn, "references",
                        lambda day=None: [{"day": "2026-11-01", "period": "місяць",
                                           "text": "листопад"}])
    first = mood2.wide_entries(DAY)
    second = mood2.wide_entries(DAY)
    assert calls == ["wide"], "the second run reads the cache"
    assert first == second


def test_a_changed_text_is_read_again(monkeypatch, tmp_path):
    calls = []
    texts = ["листопад"]

    def fake_call(stage, prompt):
        calls.append(stage)
        return json.dumps(ENTRIES, ensure_ascii=False)

    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"v2-{key}")
    monkeypatch.setattr(astro_learn, "references",
                        lambda day=None: [{"day": "2026-11-01", "period": "місяць",
                                           "text": texts[0]}])
    mood2.wide_entries(DAY)
    texts[0] = "листопад, виправлений"
    mood2.wide_entries(DAY)
    assert calls == ["wide", "wide"]


def test_no_reference_costs_no_call(monkeypatch, tmp_path):
    def fake_call(stage, prompt):                        # pragma: no cover - must not run
        raise AssertionError("a day with no month and no year must not pay for a call")

    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"v2-{key}")
    monkeypatch.setattr(astro_learn, "references", lambda day=None: [])
    assert mood2.wide_entries(DAY) == []
