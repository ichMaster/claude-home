"""t1126 — the forecast as checkable claims with time windows.

The old reading described the day's air, which could neither be checked in the evening nor
used in the morning; and it was built for an eye — five blocks, 3300 characters, four minutes
of audio — while the owner listens. These tests cover the deterministic half of the new
shape: the parsing, the claims that become data, the voice copy, and the evening question
built from them. The model calls are not tested here; the prompts are.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status"))

import mood                                                             # noqa: E402
import mood_feedback                                                    # noqa: E402

ANSWER = """ДЕНЬ
Понеділок, у якому легко бути почутим не так, як ти сказав.

ПРОГНОЗ
до обіду | розмова або лист, де тебе перепитають або зрозуміють навпаки | перепитування про гроші чи спільні домовленості
16:00-18:00 | найкоротший запал за день | дрібниця, яка в інший день пройшла б, зачепить

ДІЯ
Не ставити крапку в грошових домовленостях і нічого не підписувати.

ДУГА
Робота тягне вперед сама — це тримається з вересня й буде до зими.

ОСНОВА
Меркурій квадратура ASC (0.4°), точно зараз, до 05.11 · Місяць із Марсом ~15:50
"""


# --- TC1: the blocks --------------------------------------------------------------------

def test_the_new_blocks_parse():
    got = mood.split_blocks(ANSWER)
    assert set(("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА", "ОСНОВА")) <= set(got)
    assert got["ДЕНЬ"].startswith("Понеділок")


def test_a_missing_block_is_empty_not_fatal():
    got = mood.split_blocks("ДЕНЬ\nсам день\n")
    assert got["ДЕНЬ"] == "сам день" and got.get("ПРОГНОЗ", "") == ""


# --- TC2: claims become data ------------------------------------------------------------

def test_every_claim_carries_a_window_and_a_sign():
    got, dropped = mood.claims(ANSWER)
    assert dropped == 0 and len(got) == 2
    assert got[0]["window"] == "до обіду"
    assert "перепитають" in got[0]["claim"]
    assert "гроші" in got[0]["sign"]


@pytest.mark.parametrize("line", [
    "просто твердження без вікна й ознаки",
    "до обіду | лише твердження",
    "| твердження | ознака",
    "до обіду | | ознака",
])
def test_a_claim_without_a_window_or_a_sign_is_dropped_and_counted(line):
    text = f"ДЕНЬ\nх\n\nПРОГНОЗ\n{line}\n\nДІЯ\nх\n"
    got, dropped = mood.claims(text)
    assert got == [] and dropped == 1, "a claim that cannot be checked is not a claim"


def test_the_claims_are_capped():
    lines = "\n".join(f"{i}:00-{i+1}:00 | твердження {i} | ознака {i}" for i in range(9, 15))
    got, _ = mood.claims(f"ПРОГНОЗ\n{lines}\n")
    assert len(got) <= mood.MAX_CLAIMS


# --- TC3: what the voice says -----------------------------------------------------------

def test_the_spoken_copy_drops_the_reference_and_the_header():
    message = mood.astro_message(date(2026, 11, 2), mood.forecast_parts(ANSWER))
    said = mood.spoken(message)
    assert "Меркурій квадратура" not in said, "ОСНОВА is text only"
    assert "🜚" not in said and "Астрологія на" not in said
    assert "легко бути почутим" in said


@pytest.mark.parametrize("bad", ["0.4°", "05.11", "(2.1°)", "25.10"])
def test_a_degree_or_a_date_never_reaches_the_voice(bad):
    said = mood.scrub_voice(f"Щось таке {bad} і далі текст.")
    assert bad not in said and "Щось таке" in said


def test_scrubbing_keeps_a_clock_time():
    said = mood.scrub_voice("Між 16:00 і 18:00 буде вузько.")
    assert "16:00" in said and "18:00" in said


# --- TC4: the budget --------------------------------------------------------------------

def test_a_reading_inside_the_budget_is_untouched(monkeypatch):
    monkeypatch.setattr(mood, "run_claude",
                        lambda *a, **k: pytest.fail("no call for a short reading"))
    assert mood.fit_budget(ANSWER) == ANSWER


def test_a_reading_over_the_budget_is_compressed(monkeypatch):
    calls = []
    monkeypatch.setattr(mood, "run_claude",
                        lambda *a, **k: (calls.append(1), "ДЕНЬ\nкоротше\n")[1])
    # the overshoot has to be in a spoken block: ОСНОВА is text only and does not count
    long = ANSWER.replace("Робота тягне вперед сама", "Робота тягне вперед сама " + "я" * 4000)
    assert "коротше" in mood.fit_budget(long)
    assert calls, "the compress stage has to run"


# --- TC5: storage -----------------------------------------------------------------------

def test_claims_are_stored_per_day_and_replaced_not_duplicated(tmp_path, monkeypatch):
    f = tmp_path / "forecast-claims.jsonl"
    monkeypatch.setattr(mood, "CLAIMS", f)
    day = date(2026, 11, 2)
    got, _ = mood.claims(ANSWER)
    mood.save_claims(day, got)
    mood.save_claims(day, got)
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 2, "one run replaces the previous run's claims for that day"
    assert all(r["day"] == "2026-11-02" for r in rows)
    assert {r["id"] for r in rows} == {"2026-11-02-1", "2026-11-02-2"}
    assert mood.load_claims(day, f) == rows


def test_claims_are_per_subject(tmp_path, monkeypatch):
    """t1131: every other state file is per subject, but the claims were shared — so a
    --subject run deleted the owner's claims for the day, and the 21:00 question asked the
    owner whether someone else's predicted states happened."""
    monkeypatch.setattr(mood, "path", lambda key, default=None:
                        tmp_path / "forecast-claims.jsonl")
    monkeypatch.setattr(mood, "CLAIMS", None)
    got, _ = mood.claims(ANSWER)
    day = date(2026, 11, 2)

    monkeypatch.setattr(mood.astro, "SUBJECT", None)
    owner_file = mood.claims_file()
    mood.save_claims(day, got)

    monkeypatch.setattr(mood.astro, "SUBJECT", "kira")
    assert mood.claims_file() != owner_file, "a subject must get its own claims file"
    mood.save_claims(day, got[:1])

    monkeypatch.setattr(mood.astro, "SUBJECT", None)
    assert len(mood.load_claims(day)) == 2, "the owner's claims survive a subject run"
    monkeypatch.setattr(mood.astro, "SUBJECT", "kira")
    assert len(mood.load_claims(day)) == 1


def test_another_day_is_not_touched(tmp_path, monkeypatch):
    f = tmp_path / "forecast-claims.jsonl"
    monkeypatch.setattr(mood, "CLAIMS", f)
    got, _ = mood.claims(ANSWER)
    mood.save_claims(date(2026, 11, 1), got[:1])
    mood.save_claims(date(2026, 11, 2), got)
    assert len(mood.load_claims(date(2026, 11, 1), f)) == 1
    assert len(mood.load_claims(date(2026, 11, 2), f)) == 2


# --- TC6: the evening question ----------------------------------------------------------

def test_the_question_is_built_from_the_claims():
    got, _ = mood.claims(ANSWER)
    text = mood_feedback.questions(got)
    assert "до обіду" in text and "16:00-18:00" in text
    assert "перепитають" in text or "перепитали" in text
    for planet in ("Меркурій", "Місяць", "Сатурн", "дім"):
        assert planet not in text, "the question asks about the day, not about astrology"


def test_no_claims_means_no_question():
    assert mood_feedback.questions([]) == ""


def test_the_question_invites_a_miss():
    got, _ = mood.claims(ANSWER)
    text = mood_feedback.questions(got)
    assert "не влучило" in text or "не було" in text


def test_the_question_asks_about_a_feeling_not_an_event():
    """«Астрологія показує які емоції і бажання будуть, а не події» (the owner,
    2026-11-01). So the question asks whether the state was there."""
    got, _ = mood.claims(ANSWER)
    text = mood_feedback.questions(got)
    assert "чи було так, що" in text
    assert "Було таке?" not in text


def test_the_prompts_forbid_predicting_events():
    """The frame lives in the prompts, so this is where it is guarded: the first rework
    turned the reading into event prediction, which is a different discipline."""
    for name in ("pick.md", "day.md", "check.md"):
        text = (ROOT / "status" / "mood" / name).read_text(encoding="utf-8")
        assert "емоції й бажання" in text or "емоція або бажання" in text, name
        assert "не поді" in text or "а не які стануться події" in text, name


# --- TC7: the score ---------------------------------------------------------------------

def test_the_score_counts_hits_and_misses(tmp_path):
    rows = [{"day": "2026-11-01", "id": "a", "verified": True},
            {"day": "2026-11-01", "id": "b", "verified": False},
            {"day": "2026-11-02", "id": "c", "verified": True},
            {"day": "2026-11-02", "id": "d", "verified": None}]
    got = mood_feedback.score_rows(rows)
    assert got["hits"] == 2 and got["misses"] == 1 and got["unanswered"] == 1
    assert got["rate"] == pytest.approx(2 / 3)


def test_nothing_answered_is_said_plainly(tmp_path):
    got = mood_feedback.score_rows([{"day": "2026-11-01", "id": "a", "verified": None}])
    assert got["rate"] is None


# --- TC8: the message -------------------------------------------------------------------

def test_the_message_is_assembled_in_the_new_order():
    message = mood.astro_message(date(2026, 11, 2), mood.forecast_parts(ANSWER))
    body = message.index("легко бути почутим")
    action = message.index("Не ставити крапку")
    arc = message.index("Робота тягне")
    basis = message.index("Меркурій квадратура")
    assert body < action < arc < basis


def test_the_old_blocks_are_gone():
    """The five-block shape is what did not read (the owner, 2026-11-01)."""
    for old in ("КОРОТКО", "ПІДСУМОК", "ІСТОРІЯ", "ГОЛОВНЕ", "НАСАМКІНЕЦЬ"):
        assert old not in mood.BLOCKS_SENT


# --- the check's correction must actually be used ----------------------------------------

CHECKED = """ВИПРАВЛЕНО
ДЕНЬ
Виправлений день.

ПРОГНОЗ
11:20-13:20 | виправлене твердження | виправлена ознака

ДІЯ
Виправлена дія.

ДУГА
Виправлена дуга.

ОСНОВА
Факти з цифрами 0.2°

ОЦІНКА
вікно звужено, друкарська помилка виправлена
"""


def test_the_correction_is_what_gets_sent():
    """The first live run sent the unchecked text: `ВИПРАВЛЕНО` holds its own ДЕНЬ/ПРОГНОЗ
    markers, so splitting by marker cut the correction off at the first of them and the
    fallback kept the draft — typo, wrong window and all (t1126)."""
    got = mood.corrected(CHECKED)
    assert "Виправлений день" in got and "11:20-13:20" in got
    assert "ОЦІНКА" not in got and "вікно звужено" not in got
    parts = mood.forecast_parts(got)
    assert parts["day"] == "Виправлений день."
    assert "виправлене твердження" in parts["claims"]


def test_an_answer_without_the_marker_yields_nothing():
    assert mood.corrected("ОЦІНКА\nбез правок\n") == ""
    assert mood.corrected("") == ""


def test_a_correction_that_lost_the_structure_is_refused():
    assert mood.corrected("ВИПРАВЛЕНО\nсаме лише речення\n\nОЦІНКА\nх\n") == ""


# --- the state the `mood` probe reads ----------------------------------------------------

def test_the_state_is_written_with_the_new_keys(tmp_path, monkeypatch):
    """The live run crashed here: `save_state` still asked for `forecast["summary"]`, a key
    of the old five-block shape — four minutes of model time spent and nothing sent (t1126).
    """
    f = tmp_path / "mood.json"
    monkeypatch.setattr(mood, "state_path", lambda key: f)
    parts = mood.forecast_parts(ANSWER)
    parts["claim_list"] = mood.claims(ANSWER)[0]
    mood.save_state(date(2026, 11, 2),
                    {"figures": "ф", "conclusion": "висновок"}, parts, "ф")
    got = json.loads(f.read_text(encoding="utf-8"))
    assert got["day"] == "2026-11-02" and got["bio_conclusion"] == "висновок"
    # what the probe shows: the day's sentence plus the claims, not an old block name
    assert "Понеділок" in got["summary"]
    assert "до обіду" in got["summary"]
    assert len(got["claims"]) == 2


def test_the_state_carries_every_key_the_probe_reads(tmp_path, monkeypatch):
    """The probe is a separate script: it reads `day`, `summary`, `biorhythms` and
    `bio_conclusion` out of this file, so those names are a contract (`status/probes/mood.py`
    and `status/probes/bio.py`)."""
    probe = (ROOT / "status" / "probes" / "mood.py").read_text(encoding="utf-8")
    bio_probe = (ROOT / "status" / "probes" / "bio.py").read_text(encoding="utf-8")
    f = tmp_path / "mood.json"
    monkeypatch.setattr(mood, "state_path", lambda key: f)
    parts = mood.forecast_parts(ANSWER)
    parts["claim_list"] = mood.claims(ANSWER)[0]
    mood.save_state(date(2026, 11, 2), {"figures": "ф", "conclusion": "в"}, parts, "ф")
    written = json.loads(f.read_text(encoding="utf-8"))
    for name in ("day", "summary", "biorhythms", "bio_conclusion"):
        if f'"{name}"' in probe or f'"{name}"' in bio_probe or f"'{name}'" in probe:
            assert name in written, f"the probe reads {name} and the state must carry it"


def test_a_field_label_written_into_the_field_is_stripped():
    """The first live run came back with «ознака: відкладеш роботу» inside the sign — the
    model repeated the column name, and the evening question then read it aloud (t1126)."""
    text = ("ПРОГНОЗ\nвікно: до обіду | що станеться: прийде лист | ознака: відкладеш "
            "роботу\n")
    got, dropped = mood.claims(text)
    assert dropped == 0 and got[0]["window"] == "до обіду"
    assert got[0]["claim"] == "прийде лист" and got[0]["sign"] == "відкладеш роботу"


def test_the_question_cleans_a_label_that_is_already_stored():
    """Rows written before the parser learned to strip a label are still on disk, and the
    question must not read «ознака:» aloud because of them (t1126)."""
    stored = [{"window": "до обіду", "claim": "прийде лист",
               "sign": "ознака: відкладеш роботу"}]
    text = mood_feedback.questions(stored)
    assert "ознака:" not in text and "відкладеш роботу" in text


# --- t1126: one window, several readings -------------------------------------------------

VARIANTS = """ПРОГНОЗ
11:00-13:00 | тягне до чогось теплого і не до справ | написати тому, про кого думаєш або потягне в самоту або накриє ностальгія
17:00-18:00 | хочеться дотиснути давнє | доробити висяче або перебрати старі файли
"""


def test_a_window_carries_several_readings():
    """«Це дуже однозначно, тому що для кожного вікна може бути декілька інтерпретацій»
    (the owner, 2026-11-01). One aspect is a family of states, not one."""
    got, dropped = mood.claims(VARIANTS)
    assert dropped == 0 and len(got) == 2
    assert got[0]["variants"] == ["написати тому, про кого думаєш", "потягне в самоту",
                                  "накриє ностальгія"]
    assert len(got[1]["variants"]) == 2


def test_the_question_asks_which_reading_it_was():
    got, _ = mood.claims(VARIANTS)
    text = mood_feedback.questions(got)
    assert "Як це вийшло" in text and "або" in text
    assert "Чи нічого з цього?" in text


def test_the_variant_that_landed_is_what_is_stored(tmp_path, monkeypatch):
    f = tmp_path / "claims.jsonl"
    monkeypatch.setattr(mood, "CLAIMS", f)
    got, _ = mood.claims(VARIANTS)
    mood.save_claims(date(2026, 11, 2), got)
    rows = mood.load_claims(date(2026, 11, 2), f)
    assert rows[0]["variants"] and rows[0]["verified"] is None


def test_a_landed_variant_counts_as_a_hit():
    """`verified` carries which reading it was, so the score has to count a string as a
    hit — that string is the thing worth learning about this chart."""
    rows = [{"verified": "потягне в самоту"}, {"verified": False}, {"verified": None},
            {"verified": True}]
    got = mood_feedback.score_rows(rows)
    assert got["hits"] == 2 and got["misses"] == 1 and got["unanswered"] == 1


@pytest.mark.parametrize("raw,want", [
    ("а, або б, або в", ["а", "б", "в"]),
    ("а; б;", ["а", "б"]),
    ("а або б.", ["а", "б"]),
])
def test_a_variant_keeps_no_trailing_punctuation(raw, want):
    """The model writes «, або», so splitting on «або» left «складне,» — and the evening
    question read it as «складне,, або» (t1126)."""
    got, _ = mood.claims(f"ПРОГНОЗ\nдо обіду | тема | {raw}\n")
    assert got[0]["variants"] == want


def test_the_question_cleans_stored_punctuation():
    stored = [{"window": "до обіду", "claim": "тема",
               "variants": ["перше,", "друге,"], "sign": ""}]
    text = mood_feedback.questions(stored)
    assert ",," not in text and "перше, або друге" in text
