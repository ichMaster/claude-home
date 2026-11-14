"""t1175 — a moved occurrence of a recurring event must not be listed twice.

Google's ICS carries the master VEVENT (RRULE intact) plus an override VEVENT with
RECURRENCE-ID and the new DTSTART; ignoring RECURRENCE-ID expanded the master to the old
time *and* listed the override — a phantom slot beside the real one.
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cal_probe", ROOT / "status" / "probes" / "cal.py")
cal = importlib.util.module_from_spec(spec)
sys.modules["cal_probe"] = cal
spec.loader.exec_module(cal)

TZ = ZoneInfo("Europe/Kyiv")

ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:ev1@test
DTSTART;TZID=Europe/Kyiv:20261112T100000
DTEND;TZID=Europe/Kyiv:20261112T110000
RRULE:FREQ=WEEKLY
SUMMARY:Зустріч
END:VEVENT
BEGIN:VEVENT
UID:ev1@test
RECURRENCE-ID;TZID=Europe/Kyiv:20261119T100000
DTSTART;TZID=Europe/Kyiv:20261119T150000
DTEND;TZID=Europe/Kyiv:20261119T160000
SUMMARY:Зустріч
END:VEVENT
END:VCALENDAR
"""


def window(day):
    lo = datetime(2026, 11, day, 0, 0, tzinfo=TZ)
    hi = datetime(2026, 11, day, 23, 59, tzinfo=TZ)
    return lo, hi


def test_a_moved_occurrence_is_listed_once_at_the_new_time():
    """TC1: the week of the move shows 15:00 only — 10:00 no longer exists."""
    got = cal.events(ICS, *window(19))
    assert [e["start"].hour for e in got] == [15]


def test_an_untouched_week_keeps_the_original_time():
    """TC2: the master still expands where nothing was moved."""
    got = cal.events(ICS, *window(26))
    assert [e["start"].hour for e in got] == [10]


def test_exdate_still_drops_a_cancelled_occurrence():
    """TC3: deletions keep working beside moves."""
    ics = ICS.replace("RRULE:FREQ=WEEKLY",
                      "RRULE:FREQ=WEEKLY\nEXDATE;TZID=Europe/Kyiv:20261126T100000")
    assert cal.events(ics, *window(26)) == []


# --- t1180: VALUE=DATE-TIME is not VALUE=DATE -------------------------------------------------

def test_an_explicit_datetime_value_is_a_timed_event():
    """TC1 (t1180): a valid non-Google feed writes the default type out loud; one such
    event used to raise in the all-day branch and mark the whole calendar «не прочитано»."""
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:dt1@test
DTSTART;VALUE=DATE-TIME;TZID=Europe/Kyiv:20261118T100000
DTEND;VALUE=DATE-TIME;TZID=Europe/Kyiv:20261118T110000
SUMMARY:Нарада
END:VEVENT
END:VCALENDAR
"""
    got = cal.events(ics, *window(18))
    assert [(e["start"].hour, e["allday"]) for e in got] == [(10, False)]


def test_a_real_allday_event_still_reads_as_allday():
    """TC2 (t1180): the token fix must not lose the genuine all-day form."""
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:ad1@test
DTSTART;VALUE=DATE:20261118
DTEND;VALUE=DATE:20261119
SUMMARY:День без годин
END:VEVENT
END:VCALENDAR
"""
    got = cal.events(ics, *window(18))
    assert [e["allday"] for e in got] == [True]


# --- t1181: a date-form or naive UNTIL must not collapse the recurrence -----------------------

ALLDAY_UNTIL = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:au1@test
DTSTART;VALUE=DATE:20261101
DTEND;VALUE=DATE:20261102
RRULE:FREQ=WEEKLY;UNTIL=20261122
SUMMARY:Щотижневе без годин
END:VEVENT
END:VCALENDAR
"""


def test_a_recurring_allday_event_with_until_is_listed():
    """TC1 (t1181): Google's own export shape — date DTSTART, date UNTIL — used to make
    rrulestr raise and the whole series silently vanish into the first occurrence."""
    got = cal.events(ALLDAY_UNTIL, *window(15))     # 2026-11-15 is a Sunday occurrence
    assert [e["summary"] for e in got] == ["Щотижневе без годин"]


def test_the_until_bound_still_holds():
    """TC2 (t1181): the normalised UNTIL still ends the series where he ended it."""
    assert cal.events(ALLDAY_UNTIL, *window(29)) == []


def test_a_naive_datetime_until_expands_too():
    """TC3 (t1181): a feed that forgets the Z suffix is read as local time, not dropped."""
    ics = ICS.replace("RRULE:FREQ=WEEKLY", "RRULE:FREQ=WEEKLY;UNTIL=20261231T000000")
    got = cal.events(ics, *window(26))
    assert [e["start"].hour for e in got] == [10]


# --- t1182: every EXDATE line counts, not only the first --------------------------------------

def test_two_exdate_lines_both_exclude():
    """TC1 (t1182): Google writes one EXDATE line per deleted occurrence; the second
    deleted week used to come back from the dead."""
    ics = ICS.replace("RRULE:FREQ=WEEKLY",
                      "RRULE:FREQ=WEEKLY\n"
                      "EXDATE;TZID=Europe/Kyiv:20261126T100000\n"
                      "EXDATE;TZID=Europe/Kyiv:20261203T100000")
    assert cal.events(ics, *window(26)) == []
    dec3 = (datetime(2026, 12, 3, 0, 0, tzinfo=TZ), datetime(2026, 12, 3, 23, 59, tzinfo=TZ))
    assert cal.events(ics, *dec3) == []


def test_a_comma_separated_exdate_still_works():
    """TC2 (t1182): the single-line, multi-date form must not regress."""
    ics = ICS.replace("RRULE:FREQ=WEEKLY",
                      "RRULE:FREQ=WEEKLY\n"
                      "EXDATE;TZID=Europe/Kyiv:20261126T100000,20261203T100000")
    assert cal.events(ics, *window(26)) == []
