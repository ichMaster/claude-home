"""t1143 — phase 1: his calendar is the only sky, so fidelity is the whole contract.

Two failure modes matter and both are counted rather than judged: a loud window silently
dropped would make the reading say the day was quiet, and an invented position would put a
claim in his mouth. The fixture is synthetic — a day in his layout with invented values —
because his real calendar is a paid personal product and never enters the repository.
"""
import json
from datetime import date
from pathlib import Path

import pytest

import mood2

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (Path(__file__).parent / "data" / "reference-day.txt").read_text()
DAY = date(2026, 11, 11)

# What a correct `read` returns for that fixture: the frame, the void, the ingress, two
# windows, the natal hit under the loud one, and the multi-day span.
ITEMS = [
    {"id": "p1", "kind": "moon_sign", "from": None, "to": None, "weight": 0,
     "bodies": "Місяць", "house": None, "formula": "", "meaning": "Настрій на широкі плани.",
     "natal": None, "span": None},
    {"id": "p2", "kind": "moon_house", "from": None, "to": None, "weight": 0,
     "bodies": "Місяць", "house": "6", "formula": "",
     "meaning": "Час дрібних справ і порядку.", "natal": None, "span": None},
    {"id": "p3", "kind": "void", "from": "09:00", "to": "11:00", "weight": 0,
     "bodies": "Місяць", "house": None, "formula": "",
     "meaning": "Останні хвилини впертості.", "natal": None, "span": None},
    {"id": "p4", "kind": "ingress", "from": "11:00", "to": None, "weight": 0,
     "bodies": "Місяць", "house": None, "formula": "", "meaning": "Настрій на широкі плани.",
     "natal": None, "span": None},
    {"id": "p5", "kind": "window", "from": "12:00", "to": "15:00", "weight": 1,
     "bodies": "Нептун", "house": "2", "formula": "(☽2°♐△♆2°♈)",
     "meaning": "Час мрії.", "natal": None, "span": None},
    {"id": "p6", "kind": "window", "from": "16:00", "to": "20:00", "weight": 5,
     "bodies": "Уран", "house": "4", "formula": "(☽5°♐☍♅5°♊)",
     "meaning": "Провокації на непередбачувану розмову.", "natal": None, "span": None},
    {"id": "p7", "kind": "natal", "from": "16:00", "to": "20:00", "weight": 5,
     "bodies": "Уран", "house": "4", "formula": "(♅□♀)",
     "meaning": "Напруга між тягою до новизни і тим, що вже дороге.",
     "natal": "Венера(-)", "span": "понад місяць"},
    {"id": "p8", "kind": "span", "from": None, "to": None, "weight": 2,
     "bodies": "Марс і Кету", "house": None, "formula": "(♂26°♌☌☋26°♌)",
     "meaning": "Енергійне минуле стукає у двері.", "natal": None, "span": "по 21.11"},
]


# --- the fidelity check ---------------------------------------------------------------------

def test_correct_structure_passes():
    assert mood2.check_items(ITEMS, SOURCE) == []


def test_dropped_loud_window_is_caught():
    """The failure that would quietly turn a loud day into a quiet one."""
    without = [i for i in ITEMS if i["id"] != "p6"]
    problems = mood2.check_items(without, SOURCE)
    assert any("голосних" in p for p in problems), problems


def test_dropped_void_is_caught():
    without = [i for i in ITEMS if i["kind"] != "void"]
    assert any("холостої" in p for p in problems_of(without)), problems_of(without)


def test_dropped_natal_hit_is_caught():
    without = [i for i in ITEMS if i["kind"] != "natal"]
    assert any("натальних" in p for p in problems_of(without)), problems_of(without)


def test_invented_natal_hit_is_caught():
    """t1146 — the day names no natal hit, yet the model returns one: a claim put in his
    mouth, and mandatory_ids would force it into the reading."""
    src = SOURCE.replace("Событие влияет", "").replace("Подія впливає", "")
    problems = mood2.check_items(ITEMS, src)
    assert any("натальних" in p for p in problems), problems


def problems_of(items):
    return mood2.check_items(items, SOURCE)


@pytest.mark.parametrize("broken,needle", [
    ({"kind": "погода"}, "невідомий вид"),
    ({"meaning": "  "}, "порожнє трактування"),
    ({"weight": 9}, "поза межами"),
    ({"weight": "три"}, "поза межами"),
])
def test_malformed_position_is_caught(broken, needle):
    items = [dict(i) for i in ITEMS]
    items[4].update(broken)
    assert any(needle in p for p in mood2.check_items(items, SOURCE))


def test_duplicate_ids_are_caught():
    items = [dict(i) for i in ITEMS]
    items[1]["id"] = items[0]["id"]
    assert any("однакові id" in p for p in mood2.check_items(items, SOURCE))


def test_empty_structure_is_caught():
    assert mood2.check_items([], SOURCE)
    assert mood2.check_items("не масив", SOURCE)


# --- reading the model's answer --------------------------------------------------------------

def test_json_survives_fences_and_chatter():
    answer = "Ось результат:\n```json\n" + json.dumps(ITEMS, ensure_ascii=False) + "\n```\n"
    assert [i["id"] for i in mood2.json_answer(answer)] == [i["id"] for i in ITEMS]


def test_junk_answer_fails_clearly():
    with pytest.raises(mood2.Unfaithful):
        mood2.json_answer("не можу")
    with pytest.raises(mood2.Unfaithful):
        mood2.json_answer("[1, 2,")


# --- TC1: the mandatory positions cannot be dropped ------------------------------------------

def test_mandatory_is_every_loud_window_and_every_natal_hit():
    """Blocks, not lines: the loud window leads, the hit on the natal chart travels with it."""
    assert mood2.mandatory_ids(ITEMS) == ["p6"]
    assert [i["id"] for i in mood2.blocks(ITEMS)["p6"]] == ["p6", "p7"]


def test_a_natal_hit_cannot_be_spoken_without_its_window():
    assert mood2.expand(["p7"], ITEMS) == ["p6", "p7"]
    assert mood2.block_of("p7", ITEMS) == "p6"


def test_two_natal_lines_may_share_one_interpretation():
    """His own layout: two hits, «на мой <планета>(-):▼» and «на мой <планета>(+):▲», under
    one paragraph. The silent one is legitimate; a nameless one is not."""
    items = [dict(i) for i in ITEMS]
    items.append({**ITEMS[6], "id": "p9", "natal": "Юпітер(+)", "meaning": ""})
    assert mood2.check_items(items, SOURCE) == []
    items[-1]["natal"] = ""
    assert any("без планети" in p for p in mood2.check_items(items, SOURCE))


def test_his_direction_flag_is_kept_and_validated():
    items = [dict(i) for i in ITEMS]
    items[6]["flag"] = "▼"
    assert mood2.check_items(items, SOURCE) == []
    items[6]["flag"] = "добре"
    assert any("невідомий знак" in p for p in mood2.check_items(items, SOURCE))


def test_selection_restores_what_the_model_left_out(monkeypatch):
    """TC1 — the model preferred the frame and the quiet window; the loud one and the natal
    hit go back in regardless, even though that exceeds the preferred count."""
    monkeypatch.setattr(mood2, "conf2",
                        lambda key, default=None: {"loud_min": 3, "items_max": 2}.get(key, default))
    chosen = mood2.selection({"ids": ["p1", "p5"], "frame": "p1"}, ITEMS)
    assert chosen["ids"] == ["p1", "p5", "p6", "p7"]
    assert chosen["restored"] == ["p6"]
    assert chosen["blocks"] == 3, "three events, four lines"
    assert len(chosen["ids"]) > 2, "a preference must not outrank a mandatory position"


def test_selection_keeps_the_day_in_clock_order(monkeypatch):
    monkeypatch.setattr(mood2, "conf2", lambda key, default=None: 3 if key == "loud_min" else default)
    chosen = mood2.selection({"ids": ["p6", "p3", "p1"]}, ITEMS)
    assert chosen["ids"] == ["p1", "p3", "p6", "p7"]


def test_selection_throws_out_invented_positions(monkeypatch):
    """The invention guard at the selection stage: an id that is not in the day cannot pass."""
    monkeypatch.setattr(mood2, "conf2", lambda key, default=None: 3 if key == "loud_min" else default)
    chosen = mood2.selection({"ids": ["p1", "p42"]}, ITEMS)
    assert "p42" not in chosen["ids"]
    assert chosen["unknown"] == ["p42"]


def test_selection_survives_a_shapeless_answer(monkeypatch):
    monkeypatch.setattr(mood2, "conf2", lambda key, default=None: 3 if key == "loud_min" else default)
    chosen = mood2.selection(["p1"], ITEMS)
    assert chosen["ids"] == ["p6", "p7"], "mandatory still stands when the answer is unusable"


# --- TC2: a day he has not covered ------------------------------------------------------------

def test_missing_day_stops_the_run_and_computes_nothing(monkeypatch):
    """TC2 — no calendar means silence, and `status/astro.py` is never asked for a stand-in."""
    called = []
    monkeypatch.setattr(mood2, "reference_text", lambda day: "")
    monkeypatch.setattr(mood2, "fact_text", lambda day: called.append(day) or "факти")
    monkeypatch.setattr(mood2, "call", lambda stage, prompt: pytest.fail("стадія не має бігти"))
    with pytest.raises(mood2.NoCalendar) as e:
        mood2.run(DAY)
    assert DAY.isoformat() in str(e.value)
    assert called == [], "the facts were computed for a day v2 must stay silent about"


def test_missing_day_exits_four(monkeypatch, capsys, tmp_path):
    import sys
    monkeypatch.setattr(mood2, "reference_text", lambda day: "")
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(sys, "argv", ["mood2.py", "--day", DAY.isoformat()])
    assert mood2.main() == 4
    assert "немає" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


# --- the pipeline end to end, with canned stages ----------------------------------------------

def test_pipeline_feeds_each_stage_what_it_needs(monkeypatch, tmp_path):
    seen = {}

    def fake_call(stage, prompt):
        seen[stage] = prompt
        if stage == "read":
            return json.dumps(ITEMS, ensure_ascii=False)
        if stage == "pick":
            return json.dumps({"ids": ["p1", "p3", "p6"], "frame": "p1"}, ensure_ascii=False)
        return READING

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    out = mood2.run(DAY)

    assert "Холоста Луна" in seen["read"], "the read stage must see his own text"
    assert "p6" in seen["pick"] and "Уран" in seen["pick"]
    assert "p7" in seen["day"], "the natal hit must reach the writing stage"
    assert "p5" not in seen["day"], "the unselected window must not"
    assert json.loads(out["pick"])["ids"] == ["p1", "p3", "p6", "p7"]


def test_unfaithful_read_stops_before_writing(monkeypatch, tmp_path):
    def fake_call(stage, prompt):
        assert stage == "read", "nothing may run after an unfaithful read"
        return json.dumps([i for i in ITEMS if i["kind"] != "natal"], ensure_ascii=False)

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    with pytest.raises(mood2.Unfaithful):
        mood2.run(DAY)
    assert not list(tmp_path.iterdir()), "a failed run must leave no state behind"


# --- t1150: the fixture must be nobody's real day -------------------------------------------

def test_no_test_file_repeats_a_line_of_his_real_calendar():
    """His pages are a paid personal product; a test may copy their shape, never their text.

    The whole of `tests/` is scanned, not just the fixture: the line this guard was written
    for was an inline string in another test file (t1150).
    """
    store = ROOT / "status" / "state" / "astro-reference.jsonl"
    if not store.exists():
        pytest.skip("no reference store on this machine — nothing to compare against")
    real = store.read_text(encoding="utf-8")
    for path in sorted((ROOT / "tests").rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".txt", ".md"):
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if len(line) > 25 and line in real:
                raise AssertionError(f"{path.name} copies a real line: {line!r}")


def test_the_fixture_carries_no_natal_position_of_his():
    """The leak that held the push (t1150): the pair `(♅☍☿)` implied his real Mercury."""
    assert "☿" not in SOURCE, "a Mercury pairing in a fixture is one degree from his chart"
    assert "Меркурій" not in SOURCE


# --- the reading: does it stand on the day it was given? ------------------------------------

READING = """ДЕНЬ
Доба, яка хоче планувати більше, ніж устигне. [p1]

ПРОГНОЗ
зранку | впертість на порожньому місці, починати нове не тягне [p3]
ввечері | тягне сказати різко й перевернути розмову [p6,p7]

ДІЯ
Різке лиши до ранку — воно нікуди не дінеться. [p6]

ОСНОВА
p3 09:00-11:00 холоста · p6 16:00-20:00 ✤✤✤✤✤ (☽5°♐☍♅5°♊) · p7 натал Венера
"""
CHOSEN = ["p1", "p3", "p6", "p7"]


def test_a_reading_built_on_the_day_passes():
    assert mood2.check_reading(READING, ITEMS, CHOSEN) == []


def test_an_invented_position_is_caught():
    bad = READING.replace("[p3]", "[p9]")
    assert any("яких у виборі немає" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_a_dropped_loud_window_is_caught():
    """The failure that makes a heavy day sound calm."""
    bad = READING.replace("ввечері | тягне сказати різко й перевернути розмову [p6,p7]\n", "")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert any("не прозвучала" in p for p in problems), problems


def test_a_degree_in_the_spoken_part_is_caught():
    bad = READING.replace("тягне сказати різко", "Уран у 5° тягне сказати різко")
    assert any("читає голос" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_a_missing_part_is_caught():
    assert any("нема частини ДІЯ" in p
               for p in mood2.check_reading(READING.replace("ДІЯ", "ХТОЗНА"), ITEMS, CHOSEN))


def test_an_overlong_line_is_caught():
    bad = READING.replace("впертість на порожньому місці, починати нове не тягне",
                          "впертість " * 20)
    assert any("довший за" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_the_markers_never_reach_the_ear():
    said = mood2.spoken_part(READING)
    assert "[p" not in said and "ОСНОВА" not in said
    assert "тягне сказати різко" in said


def test_the_prompts_are_no_longer_stubs():
    """Phase 1 is finished exactly when `--send` stops refusing (t1143)."""
    assert mood2.placeholders() == []


def test_a_failed_reading_is_retried_with_what_went_wrong(monkeypatch, tmp_path):
    """A dropped loud window is a fixable mistake, not a reason to stay silent (t1143)."""
    prompts = []

    def fake_call(stage, prompt):
        if stage == "read":
            return json.dumps(ITEMS, ensure_ascii=False)
        if stage == "pick":
            return json.dumps({"ids": ["p1", "p3", "p6"], "frame": "p1"}, ensure_ascii=False)
        prompts.append(prompt)
        if len(prompts) == 1:
            return READING.replace("[p6,p7]", "[p6]")          # the natal hit goes missing
        return READING

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    out = mood2.run(DAY)
    assert len(prompts) == 2, "the second attempt must have happened"
    assert "Що виправити" in prompts[1] and "p7" in prompts[1]
    assert out["day"] == READING, "the state keeps what finally passed"


def test_a_reading_that_never_passes_still_stops(monkeypatch, tmp_path):
    def fake_call(stage, prompt):
        if stage == "read":
            return json.dumps(ITEMS, ensure_ascii=False)
        if stage == "pick":
            return json.dumps({"ids": ["p1", "p3", "p6"], "frame": "p1"}, ensure_ascii=False)
        return READING.replace("[p6,p7]", "[p6]")

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    with pytest.raises(mood2.Unfaithful):
        mood2.run(DAY)
    assert not list(tmp_path.iterdir()), "a failed run leaves no state behind"


# --- t1153: the day is named in words, not in clock times -----------------------------------

@pytest.mark.parametrize("frm,to,expected", [
    ("09:00", "11:00", "зранку"),
    ("21:27", "23:27", "ввечері"),
    ("01:00", "03:00", "вночі"),
    ("12:10", "13:40", "в обід"),
    ("14:30", "17:00", "після обіду"),
    ("05:49", "11:34", "зранку"),       # five minutes of night do not make it a night window
    ("09:55", "14:28", "зранку"),       # the part it spends most of itself in wins
    ("00:10", "02:00", "вночі"),
    ("12:00", None, "в обід"),          # a moment takes the part of its start
    ("18:00", "18:00", "ввечері"),      # a boundary does not borrow the next part
    (None, None, ""),
])
def test_part_of_day(frm, to, expected):
    assert mood2.part_of_day(frm, to) == expected


def test_the_writing_stage_is_handed_the_label(monkeypatch, tmp_path):
    seen = {}

    def fake_call(stage, prompt):
        seen[stage] = prompt
        if stage == "read":
            return json.dumps(ITEMS, ensure_ascii=False)
        if stage == "pick":
            return json.dumps({"ids": ["p1", "p3", "p6"], "frame": "p1"}, ensure_ascii=False)
        return READING

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    mood2.run(DAY)
    assert '"коли": "зранку"' in seen["day"], "the morning window must arrive labelled"
    assert '"коли"' not in seen["pick"], "the label is for the writing stage only"


def test_a_clock_time_in_the_spoken_part_is_caught():
    bad = READING.replace("зранку |", "з 09:00 до 11:00 |")
    assert any("година" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_the_hours_still_live_in_osnova():
    """ОСНОВА is where the figures go, and the check must not chase them there."""
    assert "09:00-11:00" in READING and mood2.check_reading(READING, ITEMS, CHOSEN) == []


def test_osnova_never_leaves_the_log(monkeypatch):
    """The figures are an audit trail; the chat gets the reading (t1154)."""
    sent = []
    monkeypatch.setattr(mood2.mood, "send", lambda text, role="mood": sent.append(text))
    mood2.send(READING)
    assert len(sent) == 1
    assert "ОСНОВА" not in sent[0] and "°" not in sent[0] and "[p" not in sent[0]
    assert sent[0].startswith("ДЕНЬ") and "ДІЯ" in sent[0]


# --- t1155: the cause is in the sentence, and never phrased the same way twice --------------

def test_a_named_body_that_the_day_carries_passes():
    woven = READING.replace("впертість на порожньому місці",
                            "Місяць дотягує останнє в упертому знаку, і починати не тягне")
    assert mood2.check_reading(woven, ITEMS, CHOSEN) == []


def test_a_body_the_day_does_not_carry_is_caught():
    bad = READING.replace("тягне сказати різко", "Юпітер розмахує рукою, тягне сказати різко")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert any("світила, яких у добі немає" in p and "Юпітер" in p for p in problems), problems


@pytest.mark.parametrize("word", ["Місяця", "Місяцем", "Венери", "Венерою", "Луна", "Марсом"])
def test_inflected_and_russian_forms_resolve_to_the_body(word):
    assert mood2.bodies_named(f"сьогодні {word} робить своє")


def test_the_same_turn_of_phrase_twice_is_caught():
    bad = READING.replace("впертість на порожньому місці",
                          "тихо, це тому, що Місяць дотягує знак")
    bad = bad.replace("тягне сказати різко", "різко, це тому, що Уран тисне")
    assert any("більше одного разу" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_one_such_turn_is_allowed():
    once = READING.replace("впертість на порожньому місці",
                           "тихо, це тому, що Місяць дотягує знак")
    assert mood2.check_reading(once, ITEMS, CHOSEN) == []


def test_a_line_may_now_carry_a_cause_up_to_two_hundred():
    line = "зранку | " + "я" * 180 + " [p3]"
    long_one = READING.replace("зранку | впертість на порожньому місці, починати нове не тягне "
                               "[p3]", line)
    assert mood2.check_reading(long_one, ITEMS, CHOSEN) == []
