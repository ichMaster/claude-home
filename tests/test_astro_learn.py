"""t1033 — the reference is cut into days by the model, never by a header regex, and a
reference about today makes the day recompute.

t1070 — a reference ingested with `add --file` leaves the inbox, so the panel's
«чекають на внесення» stays honest and «внести» cannot duplicate the store.
"""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("noos_astro_learn",
                                               ROOT / "status" / "astro_learn.py")
learn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(learn)

WEEK = "➲ Пт 30 октября\nЛуна в Тельце\n\nВс 1 ноября\nЛуна в Близнецах"


def answer(blocks):
    """What the splitting call returns: one line of JSON and nothing else."""
    return json.dumps(blocks, ensure_ascii=False)


def test_split_uses_the_model(monkeypatch):
    """TC1: the days come from the call's answer — no month table is consulted."""
    seen = {}

    def fake_call(prompt, model="", timeout=0):
        seen["prompt"] = prompt
        return answer([{"day": "2026-10-30", "text": "Луна в Тельце"},
                       {"day": "2026-11-01", "text": "Луна в Близнецах"}])

    monkeypatch.setattr(learn, "ask", fake_call)
    got = learn.split_days(WEEK, date(2026, 10, 31))
    assert [d.isoformat() for d, _ in got] == ["2026-10-30", "2026-11-01"]
    assert got[1][1] == "Луна в Близнецах"
    assert "Луна в Тельце" in seen["prompt"], "the text has to reach the call"


def test_split_raises_on_failure(monkeypatch):
    """TC2 (reshaped by t1228): a failed or unusable call raises SplitFailed — the
    keep-whole fallback is the caller's decision, because for a week it is poison."""
    def boom(prompt, model="", timeout=0):
        raise RuntimeError("виклик не вдався")

    monkeypatch.setattr(learn, "ask", boom)
    with pytest.raises(learn.SplitFailed):
        learn.split_days(WEEK, date(2026, 10, 31))

    monkeypatch.setattr(learn, "ask", lambda *a, **k: "не знаю")
    with pytest.raises(learn.SplitFailed):
        learn.split_days(WEEK, date(2026, 10, 31))


def test_split_drops_a_malformed_block(monkeypatch):
    """TC3: trust the answer only where it is well-formed."""
    monkeypatch.setattr(learn, "ask", lambda *a, **k: answer([
        {"day": "позавчора", "text": "сміття"},
        {"day": "2026-11-01", "text": "Луна в Близнецах"},
        {"day": "2026-11-02", "text": "   "},
    ]))
    got = learn.split_days(WEEK, date(2026, 10, 31))
    assert [d.isoformat() for d, _ in got] == ["2026-11-01"]


# --- t1070: an ingested reference leaves the inbox --------------------------------------

def test_consume_moves_an_inbox_file(monkeypatch, tmp_path):
    """TC1 (regression): after a successful ingest the file is in `ingested/`, raw text
    intact, and the inbox's own listing no longer shows it."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    f = inbox / "20261031-120000-2026-10-31.txt"
    f.write_text("еталон", encoding="utf-8")
    monkeypatch.setattr(learn, "INBOX", inbox)
    moved = learn.consume(f)
    assert moved == inbox / "ingested" / f.name
    assert moved.read_text(encoding="utf-8") == "еталон"
    assert not f.exists()
    assert list(inbox.glob("*.txt")) == []


def test_consume_leaves_foreign_files_alone(monkeypatch, tmp_path):
    """TC2: `add --file` on an arbitrary path must not relocate the owner's files."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setattr(learn, "INBOX", inbox)
    f = tmp_path / "чужий.txt"
    f.write_text("не з inbox", encoding="utf-8")
    assert learn.consume(f) is None
    assert f.exists()


def test_consume_does_not_overwrite_on_collision(monkeypatch, tmp_path):
    """TC3: a name already in `ingested/` keeps its content; the newcomer gets a suffix."""
    inbox = tmp_path / "inbox"
    (inbox / "ingested").mkdir(parents=True)
    monkeypatch.setattr(learn, "INBOX", inbox)
    (inbox / "ingested" / "a.txt").write_text("старий", encoding="utf-8")
    f = inbox / "a.txt"
    f.write_text("новий", encoding="utf-8")
    moved = learn.consume(f)
    assert moved is not None and moved.name != "a.txt"
    assert (inbox / "ingested" / "a.txt").read_text(encoding="utf-8") == "старий"
    assert moved.read_text(encoding="utf-8") == "новий"


def test_add_file_consumes_the_parked_reference(monkeypatch, tmp_path):
    """TC4: the wiring — `add --file <inbox file>` records the reference and consumes
    the file."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "INBOX", inbox)
    monkeypatch.setattr(learn, "store", lambda: store)
    f = inbox / "20261031-120000-2026-10-31.txt"
    f.write_text("текст еталона", encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "--file", str(f), "--day", "2026-10-31"])
    assert learn.main() == 0
    rec = json.loads(store.read_text(encoding="utf-8").splitlines()[0])
    assert rec["text"] == "текст еталона"
    assert not f.exists(), "the ingested file must leave the inbox"
    assert (inbox / "ingested" / f.name).is_file()


# --- t1198: --period is validated, and a month or a year names its day ----------------------
# A typo («месяц») stored a record covering() could never match, and --day defaulting to
# today let a December forecast forwarded in late November feed November's mornings.

def test_an_unknown_period_is_refused(monkeypatch, tmp_path):
    """TC1 — the regression: a period covering() cannot match is refused at the door."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "текст", "--period", "месяц"])
    with pytest.raises(SystemExit) as e:
        learn.main()
    assert e.value.code == 2, "argparse's own refusal"
    assert not store.exists(), "nothing may be stored under an unmatchable period"


def test_a_month_without_a_day_is_refused(monkeypatch, tmp_path):
    """TC2 — the regression: today is a guess about which month his forecast is for."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "текст місяця", "--period", "місяць"])
    with pytest.raises(SystemExit) as e:
        learn.main()
    assert "--day" in str(e.value.code)
    assert not store.exists()


def test_a_month_with_its_day_lands_in_covering(monkeypatch, tmp_path):
    """TC3 — with the day said, the record lands in its own month and nowhere else."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "грудень попереду",
                         "--period", "місяць", "--day", "2026-12-01"])
    assert learn.main() == 0
    assert learn.covering(date(2026, 12, 15)).get("місяць") == "грудень попереду"
    assert "місяць" not in learn.covering(date(2026, 11, 20))


def _put(store, day, text, period=None):
    rec = {"day": day, "text": text}
    if period is not None:
        rec["period"] = period
    with store.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_for_day_ignores_a_month_stored_under_the_day(monkeypatch, tmp_path):
    """t1210 TC1: a месяць forward appended after the daily calendar must not replace it."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    _put(store, "2026-11-01", "денний календар", "день")
    _put(store, "2026-11-01", "весь місяць попереду", "місяць")
    assert learn.for_day(date(2026, 11, 1)) == "денний календар"


def test_for_day_is_empty_when_only_a_month_covers_the_day(monkeypatch, tmp_path):
    """t1210 TC2: no daily calendar → empty answer, so the run stops with NoCalendar."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    _put(store, "2026-12-01", "весь місяць попереду", "місяць")
    assert learn.for_day(date(2026, 12, 1)) == ""


def test_for_day_year_ignored_old_lines_still_daily(monkeypatch, tmp_path):
    """t1210 TC3: a рік record is ignored; an old line with no period stays daily."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    _put(store, "2026-01-01", "старий запис без періоду")
    _put(store, "2026-01-01", "весь рік попереду", "рік")
    assert learn.for_day(date(2026, 1, 1)) == "старий запис без періоду"


# --- t1223: a weekly reference splits into daily records or is refused --------------------
# «тиждень» was accepted and stored, but for_day() reads only «день» and covering() only
# «місяць»/«рік» — the forward was dead data and the morning raised NoCalendar for dates
# the astrologer actually covered.

def test_weekly_with_split_stores_daily_records(monkeypatch, tmp_path):
    """TC1: each split piece is one day's calendar, so it is stored as «день»."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(learn, "ask", lambda *a, **k: answer([
        {"day": "2026-11-24", "text": "Луна в Тельце"},
        {"day": "2026-11-25", "text": "Луна в Близнецах"}]))
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "тижневий текст", "--day", "2026-11-24",
                         "--period", "тиждень", "--split"])
    assert learn.main() == 0
    recs = [json.loads(line) for line in store.read_text(encoding="utf-8").splitlines()]
    assert [r["period"] for r in recs] == ["день", "день"]
    assert learn.for_day(date(2026, 11, 25)) == "Луна в Близнецах"


def test_weekly_without_split_is_refused(monkeypatch, tmp_path):
    """TC2: a whole week under one day would be unreadable — refused at the door (t1198)."""
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "тижневий текст", "--day", "2026-11-24",
                         "--period", "тиждень"])
    with pytest.raises(SystemExit) as e:
        learn.main()
    assert "--split" in str(e.value)
    assert not store.exists(), "nothing may be stored on refusal"


# --- t1228: a failed weekly split refuses instead of storing the week as one day --------

def _week_add(monkeypatch, tmp_path, ask):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "INBOX", inbox)
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(learn, "ask", ask)
    f = inbox / "20261121-050000-2026-11-23.txt"
    f.write_text(WEEK, encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "--file", str(f),
                         "--day", "2026-11-23", "--period", "тиждень", "--split"])
    return store, f


def test_failed_weekly_split_is_refused(monkeypatch, tmp_path):
    """t1228 TC1: a model failure must refuse the week — nothing stored, file kept."""
    def boom(prompt, model="", timeout=0):
        raise RuntimeError("виклик не вдався")

    store, f = _week_add(monkeypatch, tmp_path, boom)
    with pytest.raises(SystemExit) as e:
        learn.main()
    assert "не записано" in str(e.value.code)
    assert not store.exists(), "a week must never be stored as one «день» record"
    assert f.exists(), "a refused reference must stay in the inbox"


def test_prose_answer_to_weekly_split_is_refused(monkeypatch, tmp_path):
    """t1228 TC2: an unparseable answer is the same failure, said out loud."""
    store, f = _week_add(monkeypatch, tmp_path, lambda *a, **k: "не знаю, вибач")
    with pytest.raises(SystemExit):
        learn.main()
    assert not store.exists()
    assert f.exists()


def test_failed_daily_split_still_stores_whole(monkeypatch, tmp_path):
    """t1228 TC3: for a daily reference the old fallback survives — stored whole."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "INBOX", inbox)
    monkeypatch.setattr(learn, "store", lambda: store)
    monkeypatch.setattr(learn, "ask",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("впало")))
    f = inbox / "20261121-050000-2026-11-23.txt"
    f.write_text("один день тексту", encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "--file", str(f),
                         "--day", "2026-11-23", "--split"])
    assert learn.main() == 0
    rec = json.loads(store.read_text(encoding="utf-8").splitlines()[0])
    assert rec["text"] == "один день тексту" and rec["day"] == "2026-11-23"
    assert not f.exists(), "a stored daily reference is consumed as before"
