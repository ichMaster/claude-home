"""t1084 — the fact pin buttons follow the prompt's own ranking.

The prompt sorts ascending: pin 1 is critical and always first, pin 2 fits if room is
left, pin 0 never enters. «Вище» must walk toward 1 (0→2→1) and «нижче» away from it
(1→2→0) — the `pin ± 1` it replaced demoted on «вище» and could push a fact out of the
prompt, and on a pin-2 fact did nothing at all.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import memory_screen                                                     # noqa: E402
import render                                                            # noqa: E402
import server                                                            # noqa: E402


def action(monkeypatch, what, pin):
    """Run memory_action on one fact at `pin`; return the level handed to facts.py."""
    fact = {"id": "x", "pin": pin, "added": "", "tags": "", "text": "т",
            "chars": 1, "fits": True}
    monkeypatch.setattr(server.memory_screen, "facts",
                        lambda: {"in_prompt": [fact], "cut": [], "unpinned": [],
                                 "stored": 1, "max_stored": 100,
                                 "max_in_prompt": 25, "max_chars": 240})
    got = {}

    def fake_run(*cmd, timeout=300):
        got["level"] = cmd[-1]
        return True, "ок"
    monkeypatch.setattr(server, "run_script", fake_run)
    server.memory_action({"action": [what], "id": ["x"]})
    return got.get("level")


def test_up_walks_toward_critical(monkeypatch):
    """t1084 TC1/TC2 — before the fix: pin 2 stayed 2 (clamped), pin 1 demoted to 2."""
    assert action(monkeypatch, "pin_up", 2) == "1"
    assert action(monkeypatch, "pin_up", 0) == "2"
    assert action(monkeypatch, "pin_up", 1) == "1"


def test_down_walks_away_from_critical(monkeypatch):
    """t1084 TC3 — before the fix: pin 1 unpinned straight to 0, pin 2 promoted to 1."""
    assert action(monkeypatch, "pin_down", 1) == "2"
    assert action(monkeypatch, "pin_down", 2) == "0"
    assert action(monkeypatch, "pin_down", 0) == "0"


def test_a_hand_edited_pin_does_not_crash_the_post(monkeypatch):
    """t1084 TC4 — a pin outside 0/1/2 in a hand-edited file is treated as 1."""
    assert action(monkeypatch, "pin_up", 7) in ("0", "1", "2")


# --- t1114: what the prompt actually carries (full review: truth M9, security M6) --------

def test_a_fact_longer_than_the_prompt_limit_is_marked(monkeypatch):
    """M9: the screen printed in-prompt facts in full while `facts.prompt()` truncates them
    at `memory.max_fact_chars`, so six of the 25 are shown longer than the session sees."""
    import types
    rows = [{"file": None, "id": "f1", "pin": 1, "tags": "", "added": "2026-01-01",
             "text": "я" * 400},
            {"file": None, "id": "f2", "pin": 1, "tags": "", "added": "2026-01-02",
             "text": "коротко"}]
    monkeypatch.setattr(memory_screen, "_facts_module",
                        lambda: types.SimpleNamespace(load=lambda: rows))
    got = memory_screen.facts()
    long_one, short_one = got["in_prompt"][0], got["in_prompt"][1]
    assert long_one["truncated"] and not short_one["truncated"]
    assert long_one["in_prompt_chars"] == got["max_chars"]
    html = render.render_memory(got, {"exists": False}, [], "", "tok")
    assert "обрізаний" in html or "обрізано" in html


def test_the_screen_says_it_shows_personal_material():
    """Security M6: disclosure rule 1 names the Prompt screen as its one exception, and
    this screen shows the same facts. The exemption is the login — so the page says so,
    exactly as the Prompt screen does."""
    html = render.render_memory({"in_prompt": [], "cut": [], "unpinned": [], "stored": 0,
                                 "max_stored": 100, "max_in_prompt": 25, "max_chars": 240},
                                {"exists": False}, [], "", "tok")
    assert "за паролем" in html
