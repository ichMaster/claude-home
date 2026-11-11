#!/usr/bin/env python3
"""The moment a message was sent, written once and spoken once (t1149).

The owner listens to Telegram rather than reading it, often hours later, so Telegram's own
timestamp on the screen is not in the audio. Every outgoing message carries the moment
instead: the day and the month, never the year, and the time said the way a person says it —
"дванадцяте листопада, одинадцята година п'ять хвилин".

    stamp(dt) -> (written, spoken)

The spoken half is pure Ukrainian words on purpose: a digit read by the synthesizer lands in
the wrong case ("одинадцять година"), which is exactly the kind of thing that makes a voice
message sound like a machine reading a log.

    status/tools/timestamp.py            both forms for now
    status/tools/timestamp.py --spoken   the spoken form alone (what notify.sh asks for)
"""
from __future__ import annotations

import sys
from datetime import datetime

MONTHS = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)

# the day of the month, as a date is read aloud: "дванадцяте листопада"
_ONES_N = (
    "", "перше", "друге", "третє", "четверте", "п'яте", "шосте", "сьоме", "восьме",
    "дев'яте", "десяте", "одинадцяте", "дванадцяте", "тринадцяте", "чотирнадцяте",
    "п'ятнадцяте", "шістнадцяте", "сімнадцяте", "вісімнадцяте", "дев'ятнадцяте",
)
_TENS_N = {20: "двадцяте", 30: "тридцяте"}
_TENS_N_PREFIX = {20: "двадцять", 30: "тридцять"}

# the hour, as a feminine ordinal: "одинадцята година"
_HOURS = (
    "дванадцята", "перша", "друга", "третя", "четверта", "п'ята", "шоста", "сьома",
    "восьма", "дев'ята", "десята", "одинадцята", "дванадцята", "тринадцята",
    "чотирнадцята", "п'ятнадцята", "шістнадцята", "сімнадцята", "вісімнадцята",
    "дев'ятнадцята", "двадцята", "двадцять перша", "двадцять друга", "двадцять третя",
)

# the minute, as a feminine cardinal: "п'ять хвилин", "двадцять одна хвилина"
_ONES_F = (
    "", "одна", "дві", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять",
    "десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять", "п'ятнадцять",
    "шістнадцять", "сімнадцять", "вісімнадцять", "дев'ятнадцять",
)
_TENS_F = {20: "двадцять", 30: "тридцять", 40: "сорок", 50: "п'ятдесят"}


def day_words(day: int) -> str:
    """The day of the month as an ordinal: 1 -> перше, 21 -> двадцять перше."""
    if day < 20:
        return _ONES_N[day]
    tens, ones = day // 10 * 10, day % 10
    if ones == 0:
        return _TENS_N[tens]
    return f"{_TENS_N_PREFIX[tens]} {_ONES_N[ones]}"


def minute_words(minute: int) -> str:
    """The minute with its Ukrainian agreement: 1 -> одна хвилина, 5 -> п'ять хвилин."""
    if minute < 20:
        number = _ONES_F[minute]
    else:
        tens, ones = minute // 10 * 10, minute % 10
        number = _TENS_F[tens] if ones == 0 else f"{_TENS_F[tens]} {_ONES_F[ones]}"
    # 1, 21, 31 … take the singular; 2-4, 22-24 … the dual; the rest the plural. 11-14 are
    # the exception that makes the rule arithmetic rather than a lookup on the last digit.
    last, pair = minute % 10, minute % 100
    if last == 1 and pair != 11:
        return f"{number} хвилина"
    if last in (2, 3, 4) and pair not in (12, 13, 14):
        return f"{number} хвилини"
    return f"{number} хвилин"


def stamp(dt: datetime | None = None) -> tuple[str, str]:
    """The moment in two forms: (written for the eye, spoken for the ear)."""
    dt = dt or datetime.now()
    month = MONTHS[dt.month - 1]
    written = f"{dt.day} {month}, {dt.hour:02d}:{dt.minute:02d}"

    minutes = "рівно" if dt.minute == 0 else minute_words(dt.minute)
    if dt.hour == 0 and dt.minute == 0:
        time = "опівночі"
    elif dt.hour == 0:
        # midnight is the twelfth hour, never a zero, and "ночі" goes after the minutes
        # rather than after the hour — otherwise it splits the phrase in half.
        time = f"{_HOURS[0]} година {minutes} ночі"
    else:
        time = f"{_HOURS[dt.hour]} година {minutes}"
    spoken = f"{day_words(dt.day).capitalize()} {month}, {time}."
    return written, spoken


if __name__ == "__main__":
    written, spoken = stamp()
    if "--spoken" in sys.argv:
        print(spoken)
    elif "--written" in sys.argv:
        print(written)
    else:
        print(written)
        print(spoken)
