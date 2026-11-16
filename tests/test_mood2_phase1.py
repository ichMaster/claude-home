"""t1143 — phase 1: his calendar is the only sky, so fidelity is the whole contract.

Two failure modes matter and both are counted rather than judged: a loud window silently
dropped would make the reading say the day was quiet, and an invented position would put a
claim in his mouth. The fixture is synthetic — a day in his layout with invented values —
because his real calendar is a paid personal product and never enters the repository.
"""
import json
import sys
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
    assert "p5" in seen["day"], "every position must — nothing of his day is dropped (t1156)"
    assert "НАГОЛОС" not in seen["day"] and "p6" in seen["day"]
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
Доба, яка хоче планувати більше, ніж устигне, і ввечері впирається в різке слово. [p1,p6]

ПРОГНОЗ
зранку | Місяць дотягує впертий знак, і починати нове не тягне; Нептун додає мрійливості [p3,p5]
ввечері | Уран штовхає сказати різко, а натальна Венера робить це дорожчим, ніж здається [p6,p7]
фоном | Марс із Кету тримають енергійне минуле під дверима [p8]

ДІЯ
Різке лиши до ранку — воно нікуди не дінеться. [p6]

ОСНОВА
p3 09:00-11:00 холоста · p6 16:00-20:00 ✤✤✤✤✤ (☽5°♐☍♅5°♊) · p7 натал Венера
"""
CHOSEN = [i["id"] for i in ITEMS]          # the writing stage sees the whole day (t1156)


def test_a_reading_built_on_the_day_passes():
    assert mood2.check_reading(READING, ITEMS, CHOSEN) == []


def test_an_invented_position_is_caught():
    bad = READING.replace("[p3,p5]", "[p99]")
    assert any("яких у добі немає" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_a_dropped_loud_window_is_caught():
    """The failure that makes a heavy day sound calm."""
    bad = READING.replace(
        "ввечері | Уран штовхає сказати різко, а натальна Венера робить це дорожчим, "
        "ніж здається [p6,p7]\n", "").replace("[p1,p6]", "[p1]")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert any("не прозвучала" in p for p in problems), problems


def test_a_degree_in_the_spoken_part_is_caught():
    bad = READING.replace("Уран штовхає", "Уран у 5° штовхає")
    assert any("читає голос" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_a_missing_part_is_caught():
    assert any("нема частини ДІЯ" in p
               for p in mood2.check_reading(READING.replace("ДІЯ", "ХТОЗНА"), ITEMS, CHOSEN))


def test_an_overlong_line_is_caught():
    bad = READING.replace("Місяць дотягує впертий знак",
                          "Місяць " + "дотягує " * 80)
    assert any("довший за" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_the_markers_never_reach_the_ear():
    said = mood2.spoken_part(READING)
    assert "[p" not in said and "ОСНОВА" not in said
    assert "Уран штовхає сказати різко" in said


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
            return READING.replace(", а натальна Венера робить це дорожчим, ніж здається",
                                   "")                          # the natal hit goes missing
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
        return READING.replace(", а натальна Венера робить це дорожчим, ніж здається", "")

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
    monkeypatch.setattr(mood2.mood, "send",
                        lambda text, role="mood", voice=None, profile=None:
                        sent.append(text) or True)
    mood2.send(READING)
    assert len(sent) == 1
    assert "ОСНОВА" not in sent[0] and "°" not in sent[0] and "[p" not in sent[0]
    assert sent[0].startswith("ДЕНЬ") and "ДІЯ" in sent[0]


# --- t1155: the cause is in the sentence, and never phrased the same way twice --------------

def test_a_named_body_that_the_day_carries_passes():
    assert mood2.check_reading(READING, ITEMS, CHOSEN) == []


def test_a_body_the_day_does_not_carry_is_caught():
    bad = READING.replace("Уран штовхає", "Юпітер розмахує рукою, Уран штовхає")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert any("світила, яких у добі немає" in p and "Юпітер" in p for p in problems), problems


@pytest.mark.parametrize("word", ["Місяця", "Місяцем", "Венери", "Венерою", "Луна", "Марсом"])
def test_inflected_and_russian_forms_resolve_to_the_body(word):
    assert mood2.bodies_named(f"сьогодні {word} робить своє")


def test_the_same_turn_of_phrase_twice_is_caught():
    bad = READING.replace("Місяць дотягує впертий знак",
                          "тихо, це тому, що Місяць дотягує знак")
    bad = bad.replace("Уран штовхає", "різко, це тому, що Уран тисне")
    assert any("більше одного разу" in p for p in mood2.check_reading(bad, ITEMS, CHOSEN))


def test_one_such_turn_is_allowed():
    once = READING.replace("Місяць дотягує впертий знак",
                           "тихо, це тому, що Місяць дотягує знак")
    assert mood2.check_reading(once, ITEMS, CHOSEN) == []


def test_a_grouped_line_may_run_to_the_whole_paragraph():
    line = ("зранку | Місяць дотягує впертий знак, Нептун додає мрійливості, "
            + "і " * 80 + "далі [p3,p5]")
    long_one = READING.replace(
        "зранку | Місяць дотягує впертий знак, і починати нове не тягне; "
        "Нептун додає мрійливості [p3,p5]", line)
    assert len(line) < mood2.LINE_MAX
    assert mood2.check_reading(long_one, ITEMS, CHOSEN) == []


# --- t1156: nothing of his day disappears ---------------------------------------------------

def test_a_body_of_the_day_that_never_sounds_is_caught():
    """The defect that prompted this: a planet he supplied, gone by the time of writing."""
    bad = READING.replace("Нептун додає мрійливості", "і далі так само")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert any("яких у читанні немає" in p and "Нептун" in p for p in problems), problems


def test_the_parts_of_the_day_keep_their_order():
    lines = READING.splitlines()
    morning = next(i for i, ln in enumerate(lines) if ln.startswith("зранку"))
    evening = next(i for i, ln in enumerate(lines) if ln.startswith("ввечері"))
    swapped = lines[:]
    swapped[morning], swapped[evening] = swapped[evening], swapped[morning]
    problems = mood2.check_reading("\n".join(swapped), ITEMS, CHOSEN)
    assert any("не по порядку" in p for p in problems), problems


def test_a_lost_body_is_handed_back_to_the_retry(monkeypatch, tmp_path):
    prompts = []

    def fake_call(stage, prompt):
        if stage == "read":
            return json.dumps(ITEMS, ensure_ascii=False)
        if stage == "pick":
            return json.dumps({"ids": ["p6"], "frame": "p1"}, ensure_ascii=False)
        prompts.append(prompt)
        if len(prompts) == 1:
            return READING.replace("Нептун додає мрійливості", "і далі так само")
        return READING

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    out = mood2.run(DAY)
    assert len(prompts) == 2 and "Нептун" in prompts[1]
    assert out["day"] == READING


# --- t1157: the spoken copy breathes --------------------------------------------------------

def test_the_spoken_copy_carries_pauses_and_no_headings():
    said = mood2.voice_text(READING)
    assert said.count("[довга пауза]") >= 4, "a breath before each part of the day"
    assert "ДЕНЬ" not in said and "ПРОГНОЗ" not in said and "ОСНОВА" not in said
    assert "[p" not in said
    assert "зранку. [пауза]" in said, "the part is announced, then a breath"


def test_the_tags_never_reach_the_written_message(monkeypatch):
    seen = {}
    monkeypatch.setattr(mood2.mood, "send",
                        lambda text, role="mood", voice=None, profile=None:
                        seen.update(text=text, voice=voice, profile=profile) or True)
    mood2.send(READING)
    assert "[пауза]" not in seen["text"] and "ОСНОВА" not in seen["text"]
    assert "[довга пауза]" in seen["voice"]
    assert seen["profile"] == "zorya-reading", "the reading has its own, slower delivery"


# --- t1158: a malformed read answer is a failed check, never a crash ------------------------

def test_item_without_id_is_caught_not_crashed():
    """TC1 (t1158): one item missing its id must fail the parse cleanly — before the fix it
    passed check_items and crashed the pick stage with KeyError."""
    headless = {k: v for k, v in ITEMS[5].items() if k != "id"}
    problems = mood2.check_items([dict(ITEMS[0]), headless], "")
    assert any("без id" in p for p in problems), problems


def test_non_dict_item_is_caught_not_crashed():
    """TC2 (t1158): a stray string in the model's list must not raise AttributeError."""
    problems = mood2.check_items(["не позиція"], "")
    assert problems and any("без id" in p for p in problems), problems


# --- t1159: the nodes answer to their own canonical plural ----------------------------------

@pytest.mark.parametrize("word", ["вузли", "вузлів", "вузлами", "узлы"])
def test_node_plural_resolves_to_the_nodes(word):
    """TC1 (t1159): a correct reading that says «вузли» must count as naming the nodes."""
    assert mood2.bodies_named(f"фоном {word} тягнуть своє") == {"вузли"}


@pytest.mark.parametrize("word", ["Кету", "Раху", "вузол", "узел"])
def test_node_singular_forms_still_resolve(word):
    """TC2 (t1159): the forms that worked keep working."""
    assert mood2.bodies_named(f"фоном {word} тягне своє") == {"вузли"}


# --- t1160: a --send run that could not deliver says so in the chat -------------------------

def _fail_run_argv(monkeypatch, tmp_path, argv):
    import types
    calls = []
    monkeypatch.setattr(mood2, "reference_text", lambda day: "")
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(mood2.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or
                        types.SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(sys, "argv", argv)
    return calls


def test_failed_send_run_reports_to_the_chat(monkeypatch, tmp_path):
    """TC1 (t1160): --send with no calendar still exits 4, and notify.sh carries the why."""
    calls = _fail_run_argv(monkeypatch, tmp_path,
                           ["mood2.py", "--day", DAY.isoformat(), "--send"])
    assert mood2.main() == 4
    notifies = [c for c in calls if str(c[0]).endswith("notify.sh")]
    assert len(notifies) == 1
    assert "немає" in " ".join(str(x) for x in notifies[0])


def test_failed_run_without_send_stays_quiet(monkeypatch, tmp_path):
    """TC2 (t1160): the same failure without --send must not message anyone."""
    calls = _fail_run_argv(monkeypatch, tmp_path, ["mood2.py", "--day", DAY.isoformat()])
    assert mood2.main() == 4
    assert [c for c in calls if str(c[0]).endswith("notify.sh")] == []


def test_broken_notify_does_not_change_the_exit_code(monkeypatch, tmp_path):
    """TC3 (t1160): notify.sh blowing up must not mask the real exit code."""
    def boom(cmd, **kw):
        raise OSError("немає notify.sh")
    monkeypatch.setattr(mood2, "reference_text", lambda day: "")
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(mood2.subprocess, "run", boom)
    monkeypatch.setattr(sys, "argv", ["mood2.py", "--day", DAY.isoformat(), "--send"])
    assert mood2.main() == 4


# --- t1177: an everyday word is not the name of a body --------------------------------------

# A day with no nodes in it: p8 is the only position that carries Кету.
DAY_NO_NODES = [i for i in ITEMS if i["id"] != "p8"]
READING_NO_NODES = READING.replace(
    "фоном | Марс із Кету тримають енергійне минуле під дверима [p8]\n", "")
CHOSEN_NO_NODES = [i["id"] for i in DAY_NO_NODES]


def test_the_day_without_nodes_passes_as_written():
    """The fixture itself is sound, so a failure below is the word and not the day."""
    assert mood2.check_reading(READING_NO_NODES, DAY_NO_NODES, CHOSEN_NO_NODES) == []


def test_a_knot_of_tension_is_not_the_lunar_nodes():
    """TC1 (t1177): the word that silenced the morning of 2026-11-13.

    «вузол» is an ordinary noun long before it is Rahu and Ketu, and the day carried no
    nodes at all — so four rewrites were refused for a body nobody had named.
    """
    bad = READING_NO_NODES.replace("Різке лиши до ранку",
                                   "Вузол напруги до ранку не розв'язати, тож різке лиши")
    problems = mood2.check_reading(bad, DAY_NO_NODES, CHOSEN_NO_NODES)
    assert not any("яких у добі немає" in p for p in problems), problems


@pytest.mark.parametrize("phrase", ["вузол напруги", "розв'язати вузол", "вузол думок"])
def test_an_unqualified_knot_claims_nothing(phrase):
    """TC1 (t1177): ambiguous evidence may acquit, never convict."""
    assert mood2.bodies_claimed(f"вночі {phrase}") == set()


def test_in_the_morning_is_not_uranus():
    """TC2 (t1177): «уранці» contains «уран» and is not a planet."""
    assert mood2.bodies_named("уранці легше, ніж здавалось") == set()
    assert mood2.bodies_claimed("уранці легше, ніж здавалось") == set()


def test_a_bell_ringing_is_not_the_moon():
    """TC3 (t1177): «лунає» contains «лун» and is not the Moon."""
    assert mood2.bodies_named("лунає дзвін, і це не привід") == set()


@pytest.mark.parametrize("word", ["вузли", "вузлів", "вузлами", "узлы", "Раху", "Кету"])
def test_the_nodes_are_still_heard_when_the_day_carries_them(word):
    """TC4 (t1177): t1159 keeps working — a correct reading is not accused of losing them."""
    assert mood2.bodies_named(f"фоном {word} тягнуть своє") == {"вузли"}


def test_an_invented_body_is_still_caught():
    """TC5 (t1177): the check still does the job it exists for."""
    bad = READING_NO_NODES.replace("Уран штовхає", "Юпітер розмахує рукою, Уран штовхає")
    problems = mood2.check_reading(bad, DAY_NO_NODES, CHOSEN_NO_NODES)
    assert any("яких у добі немає" in p and "Юпітер" in p for p in problems), problems


@pytest.mark.parametrize("word,body", [
    ("Місяця", "Місяць"), ("Місяцем", "Місяць"), ("Луна", "Місяць"), ("Луны", "Місяць"),
    ("Венери", "Венера"), ("Венерою", "Венера"), ("Марсом", "Марс"),
    ("Урана", "Уран"), ("Ураном", "Уран"), ("Юпитер", "Юпітер"), ("Юпітера", "Юпітер"),
    ("Солнце", "Сонце"), ("Сонця", "Сонце"), ("Лилит", "Ліліт"), ("Ліліт", "Ліліт"),
    ("Сатурна", "Сатурн"), ("Плутоном", "Плутон"), ("Нептуна", "Нептун"),
    ("Меркурієм", "Меркурій"), ("Меркурий", "Меркурій"),
])
def test_inflected_and_russian_forms_still_resolve(word, body):
    """TC6 (t1177): the endings his pages and our readings actually use."""
    assert mood2.bodies_named(f"сьогодні {word} робить своє") == {body}
    assert mood2.bodies_claimed(f"сьогодні {word} робить своє") == {body}


def test_a_bare_knot_still_counts_as_naming_the_nodes():
    """TC7 (t1177): the asymmetry, stated as a test.

    Over a day that does carry the nodes, «вузол» counts as having named them — otherwise
    the lost-bodies count would demand a qualifier the owner never asked for.
    """
    assert mood2.bodies_named("фоном вузол тягне своє") == {"вузли"}
    bad = READING.replace("Марс із Кету тримають", "Марс і цей вузол тримають")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert not any("яких у читанні немає" in p for p in problems), problems


# --- t1179: the day's own prose must not whitelist a body ------------------------------------

# The same nodeless day, but one meaning uses «вузол» as the everyday noun it is. The t1177
# asymmetry was applied only to the reading's words; applied to the items it worked backwards:
# the loose match put «вузли» into the day, demanded them from a correct reading, and excused
# a reading that then asserted them.

def knot_day():
    items = [dict(i) for i in DAY_NO_NODES]
    items[5]["meaning"] = "Вузол напруги у розмові сам не розв'яжеться."
    return items


def test_a_knot_in_the_days_prose_demands_no_nodes():
    """TC1 (t1179): a correct nodeless reading is not refused over a word in his prose."""
    problems = mood2.check_reading(READING_NO_NODES, knot_day(), CHOSEN_NO_NODES)
    assert not any("яких у читанні немає" in p for p in problems), problems


def test_a_knot_in_the_days_prose_excuses_no_invention():
    """TC2 (t1179): asserting the lunar nodes over a nodeless day is still an invention."""
    bad = READING_NO_NODES.replace("Різке лиши до ранку",
                                   "Місячні вузли тиснуть, тож різке лиши до ранку")
    problems = mood2.check_reading(bad, knot_day(), CHOSEN_NO_NODES)
    assert any("яких у добі немає" in p and "вузли" in p for p in problems), problems


def test_bare_nodes_in_the_bodies_field_still_carry_the_day():
    """TC3 (t1179): in a structured field «вузли» can only be the nodes — no t1156 regression."""
    items = [dict(i) for i in DAY_NO_NODES]
    items[5]["bodies"] = "Уран і вузли"
    fine = READING_NO_NODES.replace("Уран штовхає сказати різко",
                                    "Уран і місячні вузли штовхають сказати різко")
    assert not any("яких у добі немає" in p
                   for p in mood2.check_reading(fine, items, CHOSEN_NO_NODES))
    problems = mood2.check_reading(READING_NO_NODES, items, CHOSEN_NO_NODES)
    assert any("яких у читанні немає" in p and "вузли" in p for p in problems), problems


# --- t1192: a heavy day is read as heavy ----------------------------------------------------
# The owner, 16 November: «максимум ✤✤ може бути 4 і якщо їх багато то ставити на цьому акцент
# в прогнозі і більше деталей в самарі». So the intensity he publishes has to reach the
# writing stage as arithmetic, and the summary of a heavy day has to name what makes it heavy.

def calm_day():
    """The same day with nothing loud in it: the top window drops to two marks."""
    items = [dict(i) for i in ITEMS]
    for item in items:
        if item["id"] in ("p6", "p7"):
            item["weight"] = 2
    return items


def quiet_day():
    """A day with no weighted position at all — the Moon and nothing else."""
    return [dict(i) for i in ITEMS[:4]]


QUIET_READING = """ДЕНЬ
Доба тиха, і це не комплімент. [p1]

ПРОГНОЗ
зранку | Місяць дотягує впертий знак, і починати нове не тягне [p3]
в обід | Місяць переходить у новий знак — тягне на широкі плани [p2,p4]

ДІЯ
Нічого не форсуй. [p1]

ОСНОВА
p3 09:00-11:00 холоста
"""


def test_pressure_counts_the_day(): 
    """TC3 — the top weight, the loud blocks and the accented ones, natal hits folded in."""
    p = mood2.pressure(ITEMS)
    assert p["top"] == 5
    assert p["loud"] == ["p6"], "p7 hangs under p6 — one heavy event, not two"
    assert p["accent"] == ["p6"]


def test_a_calm_day_has_no_accent():
    """TC2 — two marks is not loud, so nothing is demanded of the summary."""
    p = mood2.pressure(calm_day())
    assert p["top"] == 2 and p["loud"] == [] and p["accent"] == []
    assert not any("ДЕНЬ" in problem
                   for problem in mood2.check_reading(READING, calm_day(), CHOSEN))


def test_the_summary_must_name_the_heaviest():
    """TC1 — a reading whose ДЕНЬ describes the mood and skips what presses."""
    bad = READING.replace("[p1,p6]", "[p1]")
    problems = mood2.check_reading(bad, ITEMS, CHOSEN)
    assert any("ДЕНЬ" in p and "p6" in p for p in problems), problems
    assert mood2.check_reading(READING, ITEMS, CHOSEN) == []


def test_a_natal_hit_in_the_summary_counts_as_its_window():
    """The block is the unit: marking the personal hit names its window too."""
    fine = READING.replace("[p1,p6]", "[p1,p7]")
    assert mood2.check_reading(fine, ITEMS, CHOSEN) == []


def test_many_loud_windows_make_the_day_heavy():
    """TC4 — three loud blocks weigh on a day even with nothing at the top of the scale."""
    items = [dict(i) for i in ITEMS]
    for item in items:
        if item["id"] in ("p6", "p7"):
            item["weight"] = 3
    items[4]["weight"] = 3          # p5, the quiet midday window
    items[7]["weight"] = 3          # p8, the multi-day span
    p = mood2.pressure(items)
    assert p["top"] == 3 and len(p["loud"]) == 3 and p["accent"] == []
    assert mood2.is_heavy(p)
    text = mood2.pressure_text(items)
    assert "3" in text and "✤" not in text, text


def test_five_marks_are_the_top_of_the_scale():
    """TC5 — five is the top (the owner, 16 November) and it is accented, not an error."""
    assert mood2.check_items(ITEMS, SOURCE) == []
    assert mood2.pressure(ITEMS)["accent"] == ["p6"]


def test_a_quiet_day_demands_nothing_of_the_summary():
    """TC6 — no weighted position, no accent, and the pressure line says so."""
    p = mood2.pressure(quiet_day())
    assert p["top"] == 0 and p["accent"] == []
    assert not mood2.is_heavy(p)
    assert "рівна" in mood2.pressure_text(quiet_day())
    assert mood2.check_reading(QUIET_READING, quiet_day(), ["p1", "p2", "p3", "p4"]) == []


def test_the_writing_stage_is_handed_the_pressure(monkeypatch, tmp_path):
    """The emphasis is computed here, so the prompt carries it instead of counting marks."""
    prompts = {}

    def fake_call(stage, prompt):
        prompts[stage] = prompt
        if stage == "read":
            return json.dumps(ITEMS, ensure_ascii=False)
        if stage == "pick":
            return json.dumps({"ids": ["p6"]}, ensure_ascii=False)
        return READING

    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"v2-{key}")
    mood2.run(DAY, dry_run=True)
    assert "{{ТИСК}}" not in prompts["day"]
    assert mood2.pressure_text(ITEMS) in prompts["day"]
    assert "p6" in prompts["day"]


def test_a_level_day_is_handed_no_false_emphasis():
    """TC7 — nothing weighted, so the emphasis field says so instead of naming the whole day."""
    assert mood2.accent_ids(quiet_day()) == []
    assert mood2.accent_ids(ITEMS) == ["p6"]


# --- t1194: his compact notation is a pair of bodies, not one unknown word ------------------
# Measured on 15 November: `"bodies": "Солнце90Раху"` — his shorthand for a square — hid the
# Sun and the nodes from the day, so a correct reading was accused of inventing them and an
# incomplete one went unnoticed. The whole morning failed four attempts on it.

def pair_day():
    """The day with his compact pair notation in the structured fields."""
    items = [dict(i) for i in ITEMS]
    items[7] = dict(items[7], bodies="Солнце90Раху",
                    meaning="Хаос і метання між минулим і майбутнім.")
    return items


PAIR_READING = READING.replace(
    "фоном | Марс із Кету тримають енергійне минуле під дверима [p8]",
    "фоном | Сонце з вузлами тримає метання між минулим і тим, що настає [p8]")


def test_a_compact_pair_is_both_bodies():
    """TC3 — the digits are an angle, not part of a name."""
    assert mood2.bodies_named("Солнце90Марс") == {"Сонце", "Марс"}


def test_a_body_hidden_in_his_shorthand_is_not_an_invention():
    """TC1 — the regression: the day's own Sun must not be reported as invented."""
    problems = mood2.check_reading(PAIR_READING, pair_day(), CHOSEN)
    assert not any("яких у добі немає" in p for p in problems), problems


def test_a_body_hidden_in_his_shorthand_is_still_demanded():
    """TC2 — and the other direction: dropping it is still dropping a fact of his."""
    silent = READING.replace(
        "фоном | Марс із Кету тримають енергійне минуле під дверима [p8]",
        "фоном | Далеке минуле стукає у двері [p8]")
    problems = mood2.check_reading(silent, pair_day(), CHOSEN)
    assert any("яких у читанні немає" in p and "Сонце" in p for p in problems), problems


def test_an_ordinary_bodies_field_is_unchanged():
    """TC4 — the fix touches his shorthand and nothing else."""
    assert mood2.bodies_named("Марс і Кету") == {"Марс", "вузли"}
    assert mood2.check_reading(READING, ITEMS, CHOSEN) == []
