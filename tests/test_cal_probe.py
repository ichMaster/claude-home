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
