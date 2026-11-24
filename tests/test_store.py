"""t1048 — parse_due must treat an impossible dotted date as not-a-date instead of crashing
add (/task from Telegram dies), and defer must refuse an unparseable date instead of
silently wiping the existing deadline."""
import json

import pytest

import store


def test_parse_due_version_number_does_not_crash():
    """TC1: 'python 3.14' is a version, not the 3rd of month 14."""
    due, title = store.parse_due("оновити python 3.14")
    assert due is None
    assert "3.14" in title


def test_parse_due_impossible_day_does_not_crash():
    due, title = store.parse_due("звіт до 31.11")
    assert due is None
    assert "31.11" in title


def test_parse_due_valid_date_still_works():
    due, _ = store.parse_due("звіт до 30.11")
    assert due is not None and (due.day, due.month) == (30, 11)


@pytest.fixture
def task_log(tmp_path, monkeypatch):
    log = tmp_path / "tasks.jsonl"
    log.write_text(json.dumps({"op": "add", "id": "t001", "title": "тест",
                               "due": "2026-11-05", "ts": "2026-10-31T05:00:00+02:00"},
                              ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(store, "LOG", log)
    monkeypatch.setattr(store, "VIEW", tmp_path / "open.md")
    return log


def test_defer_unparseable_date_keeps_due(monkeypatch, task_log):
    """TC2: a phrase parse_due cannot read must not append due: null."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "колись-потім"])
    with pytest.raises(SystemExit):
        store.main()
    assert store.state()["t001"]["due"] == "2026-11-05"


def test_defer_empty_phrase_keeps_due(monkeypatch, task_log):
    """t1246 TC1: a forgotten date phrase must refuse, not wipe the deadline."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001"])
    with pytest.raises(SystemExit):
        store.main()
    assert store.state()["t001"]["due"] == "2026-11-05"


def test_defer_valid_date_still_works(monkeypatch, task_log):
    """TC3: a parseable defer still moves the date."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "завтра"])
    store.main()
    assert store.state()["t001"]["due"] is not None
    assert store.state()["t001"]["due"] != "2026-11-05"


# t1075 — defer must understand the same period phrases add does: the panel's weekend
# button sends «на вихідних», which parse_due alone cannot read.

def test_defer_to_the_weekend_sets_a_period_and_clears_due(monkeypatch, task_log):
    """TC1: the board's «вихідні» button must move the task, not fail every press."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "на вихідних"])
    store.main()
    t = store.state()["t001"]
    assert t["period"] and t["period"][0] == "вихідні"
    assert t["due"] is None, "a period defer clears the hard date — the date is the stronger claim"


def test_defer_to_a_date_keeps_an_existing_period(monkeypatch, task_log):
    """TC2: a date defer behaves as before and does not touch the period."""
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "на вихідних"])
    store.main()
    monkeypatch.setattr(store.sys, "argv", ["store.py", "defer", "t001", "завтра"])
    store.main()
    t = store.state()["t001"]
    assert t["due"] is not None
    assert t["period"] and t["period"][0] == "вихідні"


# t1076 — one writer at a time: next_id is a read-modify-write over the log, and two
# overlapping adds both minted the same id, silently shadowing a task.

def _run_in_thread(monkeypatch, argv):
    import threading
    monkeypatch.setattr(store.sys, "argv", argv)
    done = threading.Event()

    def go():
        try:
            store.main()
        except SystemExit:
            pass
        done.set()
    threading.Thread(target=go, daemon=True).start()
    return done


def test_add_waits_for_the_writer_lock(monkeypatch, task_log):
    """TC1: a mutating command must queue behind another writer, not race it."""
    import fcntl
    held = (task_log.parent / ".lock").open("w")
    fcntl.flock(held, fcntl.LOCK_EX)
    done = _run_in_thread(monkeypatch, ["store.py", "add", "задача під замком"])
    assert not done.wait(0.5), "add must block while another writer holds the lock"
    fcntl.flock(held, fcntl.LOCK_UN)
    assert done.wait(2), "add must proceed once the lock is released"
    assert any(v["title"] == "задача під замком" for v in store.state().values())


def test_list_ignores_the_writer_lock(monkeypatch, task_log):
    """TC2: a hung writer must never block the read-only commands the probes use."""
    import fcntl
    held = (task_log.parent / ".lock").open("w")
    fcntl.flock(held, fcntl.LOCK_EX)
    done = _run_in_thread(monkeypatch, ["store.py", "list"])
    assert done.wait(2), "list must answer while the writer lock is held"
    fcntl.flock(held, fcntl.LOCK_UN)


def test_old_defer_events_replay_unchanged(task_log):
    """TC4: a defer line without a period key must not invent or wipe one."""
    with task_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"op": "defer", "id": "t001", "due": "2026-11-07",
                            "ts": "2026-10-31T06:00:00+02:00"}) + "\n")
    t = store.state()["t001"]
    assert t["due"] == "2026-11-07"
    assert t.get("period") is None


# --- t1088: a numeric dd.mm date must roll into the next year like the named months ----

class _Nov1(store.date):
    @classmethod
    def today(cls):
        return store.date(2026, 11, 1)


def test_numeric_date_already_past_rolls_to_next_year(monkeypatch):
    """t1088 TC1 — «до 15.01» sent in November is January *next* year, exactly like
    «до 15 січня»; before the fix it became a task 290 days overdue."""
    monkeypatch.setattr(store, "date", _Nov1)
    due, _ = store.parse_due("звіт до 15.01")
    assert (due.year, due.month, due.day) == (2027, 1, 15)


def test_numeric_date_with_explicit_year_is_never_touched(monkeypatch):
    """t1088 TC2 — a spelled-out year is the user's word, past or not."""
    monkeypatch.setattr(store, "date", _Nov1)
    due, _ = store.parse_due("звіт до 15.01.2026")
    assert (due.year, due.month, due.day) == (2026, 1, 15)


def test_numeric_date_still_ahead_stays_this_year(monkeypatch):
    """t1088 TC3."""
    monkeypatch.setattr(store, "date", _Nov1)
    due, _ = store.parse_due("звіт до 15.12")
    assert (due.year, due.month, due.day) == (2026, 12, 15)


# --- t1166: a second start on a running task must not open a second run -----------------

def _log_events(path, *events):
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
                    encoding="utf-8")


def test_double_start_then_done_leaves_no_open_run(task_log):
    """TC1 (t1166): start, start, stop, done — exactly what a double-tapped /doing followed
    by /done writes. No run may stay open, or spent time grows forever."""
    _log_events(task_log,
                {"op": "add", "id": "t001", "title": "тест", "ts": "2026-11-10T10:00:00"},
                {"op": "start", "id": "t001", "ts": "2026-11-10T10:00:00"},
                {"op": "start", "id": "t001", "ts": "2026-11-10T10:05:00"},
                {"op": "stop", "id": "t001", "ts": "2026-11-10T11:00:00"},
                {"op": "done", "id": "t001", "ts": "2026-11-10T11:00:00"})
    t = store.state()["t001"]
    assert all(r["to"] is not None for r in t.get("runs", [])), \
        "відкритий run після done — факт часу росте вічно"
    assert store.minutes(t) == 60


def test_two_separate_runs_still_counted(task_log):
    """TC2 (t1166): genuinely separate runs are not merged by the guard."""
    _log_events(task_log,
                {"op": "add", "id": "t001", "title": "тест", "ts": "2026-11-10T10:00:00"},
                {"op": "start", "id": "t001", "ts": "2026-11-10T10:00:00"},
                {"op": "stop", "id": "t001", "ts": "2026-11-10T10:30:00"},
                {"op": "start", "id": "t001", "ts": "2026-11-10T12:00:00"},
                {"op": "stop", "id": "t001", "ts": "2026-11-10T12:30:00"})
    t = store.state()["t001"]
    assert len(t["runs"]) == 2
    assert store.minutes(t) == 60


# t1169 — genitive weekday forms after «до» must parse: «до п'ятниці» silently created a
# task with no due date, though the phrase is the module's own docstring example.

def _coming(weekday):
    import datetime
    today = datetime.date.today()
    return today + datetime.timedelta(days=(weekday - today.weekday()) % 7 or 7)


def test_parse_due_genitive_friday_docstring_example():
    """TC1: the docstring's own example must carry Friday's deadline."""
    due, title = store.parse_due("полагодити індексацію до п'ятниці")
    assert due == _coming(4)
    assert "п'ятниці" not in title


def test_parse_due_all_genitive_weekdays():
    """TC2: every genitive weekday after «до» parses."""
    cases = {"до понеділка": 0, "до вівторка": 1, "до середи": 2, "до четверга": 3,
             "до суботи": 5, "до неділі": 6}
    for phrase, wd in cases.items():
        due, _ = store.parse_due(f"звіт {phrase}")
        assert due == _coming(wd), phrase


def test_parse_due_genitive_modifier_apostrophe():
    """TC3: the U+02BC apostrophe variant the dict already carries elsewhere."""
    due, _ = store.parse_due("звіт до пʼятниці")
    assert due == _coming(4)


def test_parse_due_accusative_friday_still_works():
    """TC4: the old forms keep working."""
    due, _ = store.parse_due("звіт у п'ятницю")
    assert due == _coming(4)


# t1183 — «через N …» must eat the whole word and understand the singular forms.

def test_relative_days_cut_cleanly_from_the_title():
    """TC1 (t1183): the stem-only cut left «ів» in the stored title."""
    import datetime
    due, title = store.parse_due("нагадати через 5 днів про оплату")
    assert due == datetime.date.today() + datetime.timedelta(days=5)
    assert title == "нагадати про оплату"


def test_relative_one_week_parses():
    """TC2 (t1183): «тиждень» carries no contiguous «тижн» — it parsed nothing."""
    import datetime
    due, title = store.parse_due("зробити через 1 тиждень")
    assert due == datetime.date.today() + datetime.timedelta(days=7)
    assert "тиждень" not in title


def test_relative_one_day_parses():
    """TC3 (t1183): «день» has no «дн» either."""
    import datetime
    due, _ = store.parse_due("подзвонити через 1 день")
    assert due == datetime.date.today() + datetime.timedelta(days=1)


def test_relative_plural_forms_still_work():
    """TC4 (t1183): the forms that worked keep working, with clean titles."""
    import datetime
    due, title = store.parse_due("звіт через 2 тижні")
    assert due == datetime.date.today() + datetime.timedelta(days=14)
    assert title == "звіт"
    due, title = store.parse_due("звіт через 3 дні")
    assert due == datetime.date.today() + datetime.timedelta(days=3)
    assert title == "звіт"


# t1184 — one impossible dotted date must not hide a valid one further on.

def test_invalid_first_dotted_date_does_not_hide_a_valid_one(monkeypatch):
    """TC1 (t1184): «31.11 і ще 20.12» stored no deadline at all."""
    monkeypatch.setattr(store, "date", _Nov1)
    due, title = store.parse_due("оплатити 31.11 і ще 20.12 рахунок")
    assert due is not None and (due.day, due.month) == (20, 12)
    assert "31.11" in title


def test_version_numbers_still_parse_nothing():
    """TC2 (t1184): t1048 holds — no date invented from numbers."""
    due, title = store.parse_due("оновити python 3.14")
    assert due is None and "3.14" in title
    due, title = store.parse_due("звіт до 31.11")
    assert due is None and "31.11" in title


def test_first_valid_dotted_date_wins(monkeypatch):
    """TC3 (t1184): two valid dates — the earlier-written one is the deadline."""
    monkeypatch.setattr(store, "date", _Nov1)
    due, _ = store.parse_due("зустріч 20.11 або 25.11")
    assert (due.day, due.month) == (20, 11)


def test_parse_due_impossible_month_name_day_does_not_crash():
    """t1190 TC1: «до 31 листопада» is a number, not a date — the month-name branch must
    fall through instead of raising ValueError and killing add/defer."""
    due, title = store.parse_due("купити квитки до 31 листопада")
    assert due is None
    assert "31 листопада" in title


def test_parse_due_feb_29_non_leap_does_not_crash():
    """t1190 TC2: «до 29 лютого» must never raise; in a leap target year it parses, in a
    non-leap one it falls through as text."""
    due, _ = store.parse_due("звіт до 29 лютого")
    assert due is None or (due.month, due.day) == (2, 29)


def test_parse_due_impossible_month_name_then_valid_dotted():
    """t1190 TC3: an impossible month-name date before a valid dotted one still yields the
    dotted deadline, mirroring t1184."""
    due, _ = store.parse_due("здати до 31 листопада, крайній строк 20.12")
    assert due is not None and (due.month, due.day) == (12, 20)


def test_parse_due_valid_month_name_still_works():
    """t1190 TC4: a possible month-name date keeps parsing and is cut from the title."""
    due, title = store.parse_due("звіт до 20 грудня")
    assert due is not None and (due.month, due.day) == (12, 20)
    assert "грудня" not in title


# --- t1215: version and decimal numbers are numbers, not deadlines ---------------------

def test_version_after_latin_word_is_not_a_date():
    """t1215 TC1: «python 2.7» set due 2 July next year and cut the title."""
    due, title = store.parse_due("оновити python 2.7")
    assert due is None
    assert title == "оновити python 2.7"


def test_decimal_before_a_measure_word_is_not_a_date():
    """t1215 TC2: «10.5 тис» is money, not the 10th of May."""
    due, title = store.parse_due("бюджет 10.5 тис")
    assert due is None
    assert title == "бюджет 10.5 тис"


def test_real_dates_still_parse_after_the_guards():
    """t1215 TC3: the guards must not eat genuine dates."""
    due, _ = store.parse_due("зустріч 18.10 в кафе")
    assert due is not None and (due.day, due.month) == (18, 10)
    due, _ = store.parse_due("звіт до 30.11")
    assert due is not None and (due.day, due.month) == (30, 11)


# --- t1216: the decimal guard knows the full measure words and the time units -----------

def test_decimal_before_a_full_measure_word_is_not_a_date():
    """t1216 TC2: «10.5 тисяч» is money — «тис» with a \\b missed the full word."""
    due, title = store.parse_due("переказати 10.5 тисяч мамі")
    assert due is None
    assert title == "переказати 10.5 тисяч мамі"


def test_decimal_before_a_time_unit_is_not_a_date():
    """t1216 TC1: «1.5 години» is a duration, not the 1st of May."""
    due, title = store.parse_due("розмова з банком на 1.5 години")
    assert due is None
    assert title == "розмова з банком на 1.5 години"


def test_decimal_before_a_percent_word_is_not_a_date():
    """t1216 TC3: «10.5 відсотків» is a rate, not the 10th of May."""
    due, title = store.parse_due("знизити ставку на 10.5 відсотків")
    assert due is None
    assert title == "знизити ставку на 10.5 відсотків"


def test_real_dates_survive_the_broadened_guard():
    """t1216 TC4: genuine dates and the old abbreviation case stay as they were."""
    due, _ = store.parse_due("оплатити до 20.12")
    assert due is not None and (due.day, due.month) == (20, 12)
    due, title = store.parse_due("бюджет 10.5 тис")
    assert due is None and title == "бюджет 10.5 тис"


# --- t1224: duration words — days, weeks, months, years, short time units ---------------

def test_decimal_before_a_duration_word_is_not_a_date():
    """t1224 TC1: «1.5 дня» is a duration, not the 1st of May."""
    due, title = store.parse_due("відпустка на 1.5 дня")
    assert due is None
    assert title == "відпустка на 1.5 дня"


def test_decimal_before_every_duration_unit_is_not_a_date():
    """t1224 TC2: all duration units and short time forms stay numbers."""
    for text in ("бігти 2.5 год", "перерва 1.5 хв", "пауза 2.5 сек",
                 "чекати 1.5 місяця", "звіт за 2.5 тижні", "проєкт на 1.5 року"):
        due, title = store.parse_due(text)
        assert due is None, text
        assert title == text


# --- t1225: Cyrillic version words — реліз, версія, пітон ------------------------------

def test_version_after_cyrillic_version_word_is_not_a_date():
    """t1225 TC1: «реліз 3.12» is a version, not the 3rd of December."""
    due, title = store.parse_due("зробити реліз 3.12")
    assert due is None
    assert title == "зробити реліз 3.12"


def test_more_cyrillic_version_words_are_not_dates():
    """t1225 TC2: «до версії 2.5», «пітон 3.12» stay versions."""
    for text in ("оновити до версії 2.5", "перейти на пітон 3.12"):
        due, title = store.parse_due(text)
        assert due is None, text
        assert title == text


def test_ordinary_cyrillic_word_before_a_date_still_parses():
    """t1225 TC3: «зустріч 20.12» is a date — the guard stays narrow."""
    due, _ = store.parse_due("зустріч 20.12")
    assert due is not None and (due.day, due.month) == (20, 12)


# --- t1232: the duration guard must not eat genuine deadlines ---------------------------

def test_explicit_year_outranks_duration_words():
    """t1232 TC1: «до 20.12.2026 року» is a full date — a candidate with an explicit
    year can never be a decimal."""
    due, title = store.parse_due("здати звіт до 20.12.2026 року")
    assert due == store.date(2026, 12, 20)
    assert "року" in title


def test_ordinary_words_after_a_date_do_not_suppress_it():
    """t1232 TC1: «день», «тиждень», «хвіртку» are not duration measures here."""
    for text, dm in (("замовити торт на 08.03 день народження", (8, 3)),
                     ("полагодити до 15.04 хвіртку", (15, 4)),
                     ("відпустка 20.12 тиждень", (20, 12))):
        due, _ = store.parse_due(text)
        assert due is not None and (due.day, due.month) == dm, text


def test_t1224_decimals_stay_numbers_after_t1232():
    """t1232 TC2: every t1224 duration case keeps reading as a number."""
    for text in ("відпустка на 1.5 дня", "звіт за 2.5 тижні", "перерва 1.5 хв",
                 "бігти 2.5 год", "чекати 1.5 місяця", "проєкт на 1.5 року",
                 "пауза 2.5 хвилини"):
        due, title = store.parse_due(text)
        assert due is None, text
        assert title == text


def test_explicit_year_outranks_money_words():
    """t1232 TC3: the year exemption beats every measure word, not only durations."""
    due, _ = store.parse_due("бюджет до 20.12.2026 тис")
    assert due == store.date(2026, 12, 20)


# --- t1233: «на вихідних» on a Sunday means the weekend in progress ----------------------

class _Sun22(store.date):
    @classmethod
    def today(cls):
        return store.date(2026, 11, 22)      # a Sunday


def test_weekend_on_sunday_is_the_one_in_progress(monkeypatch):
    """t1233 TC1: said on Sunday, the period contains today, not next weekend."""
    monkeypatch.setattr(store, "date", _Sun22)
    period, _ = store.parse_period("перебрати акваріум на вихідних")
    kind, start, end = period
    assert kind == "вихідні"
    assert start == store.date(2026, 11, 21) and end == store.date(2026, 11, 22)


def test_weekend_on_other_days_is_unchanged(monkeypatch):
    """t1233 TC2+TC3: Saturday, Friday and Monday keep their old answers."""
    for day, sat in ((21, 21),   # Saturday → today..tomorrow
                     (20, 21),   # Friday → the coming weekend
                     (16, 21)):  # Monday → five days ahead
        class _D(store.date):
            @classmethod
            def today(cls, _d=day):
                return store.date(2026, 11, _d)
        monkeypatch.setattr(store, "date", _D)
        period, _ = store.parse_period("на вихідних")
        _, start, end = period
        assert start == store.date(2026, 11, sat), f"day {day}"
        assert end == store.date(2026, 11, sat + 1), f"day {day}"


# --- t1258: a clock time written with a dot is a time, not a date ---------------------------

def test_clock_time_after_o_is_not_a_date():
    """t1258 TC1: «о 9.05» is five past nine, not the ninth of May next year."""
    due, title = store.parse_due("подзвонити лікарю о 9.05")
    assert due is None
    assert title == "подзвонити лікарю о 9.05"


def test_clock_time_after_ob_is_not_a_date():
    """t1258 TC2: «об 11.10» is the same preposition before a vowel."""
    due, title = store.parse_due("зустріч об 11.10 з Олегом")
    assert due is None
    assert title == "зустріч об 11.10 з Олегом"


def test_plain_dotted_date_still_parses_after_an_ordinary_word():
    """t1258 TC3: a generic word before a date is the normal way to date a task, and a
    word merely ending in «о» must not trip the single-letter guard."""
    due, _ = store.parse_due("зустріч 20.12")
    assert due is not None and (due.month, due.day) == (12, 20)
    due, _ = store.parse_due("кіно 20.12")
    assert due is not None and (due.month, due.day) == (12, 20)
