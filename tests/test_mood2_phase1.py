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
     "bodies": "Місяць", "house": None, "formula": "", "meaning": "Оптимізм і запал.",
     "natal": None, "span": None},
    {"id": "p2", "kind": "moon_house", "from": None, "to": None, "weight": 0,
     "bodies": "Місяць", "house": "10", "formula": "",
     "meaning": "Час визнання для твоєї справи.", "natal": None, "span": None},
    {"id": "p3", "kind": "void", "from": "09:00", "to": "11:00", "weight": 0,
     "bodies": "Місяць", "house": None, "formula": "",
     "meaning": "Останні хвилини впертості.", "natal": None, "span": None},
    {"id": "p4", "kind": "ingress", "from": "11:00", "to": None, "weight": 0,
     "bodies": "Місяць", "house": None, "formula": "", "meaning": "Оптимізм і запал.",
     "natal": None, "span": None},
    {"id": "p5", "kind": "window", "from": "12:00", "to": "15:00", "weight": 1,
     "bodies": "Нептун", "house": "1", "formula": "(☽2°♐△♆2°♈)",
     "meaning": "Час мрії.", "natal": None, "span": None},
    {"id": "p6", "kind": "window", "from": "16:00", "to": "20:00", "weight": 5,
     "bodies": "Уран", "house": "3", "formula": "(☽5°♐☍♅5°♊)",
     "meaning": "Провокації на непередбачувану розмову.", "natal": None, "span": None},
    {"id": "p7", "kind": "natal", "from": "16:00", "to": "20:00", "weight": 5,
     "bodies": "Уран", "house": "3", "formula": "(♅☍☿)",
     "meaning": "Конфлікт між новою ідеєю і звичним мисленням.",
     "natal": "Меркурій(-)", "span": "понад місяць"},
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
            return json.dumps({"ids": ["p1", "p6"], "frame": "p1"}, ensure_ascii=False)
        return "читання"

    monkeypatch.setattr(mood2, "reference_text", lambda day: SOURCE)
    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    out = mood2.run(DAY)

    assert "Холоста Луна" in seen["read"], "the read stage must see his own text"
    assert "p6" in seen["pick"] and "Уран" in seen["pick"]
    assert "p7" in seen["day"], "the natal hit must reach the writing stage"
    assert "p5" not in seen["day"], "the unselected window must not"
    assert json.loads(out["pick"])["ids"] == ["p1", "p6", "p7"]


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
