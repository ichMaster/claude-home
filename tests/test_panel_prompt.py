"""t1101 — admin panel, phase 5: the Prompt and Scenarios screens.

The screen that justified the project: the system prompt the session actually wakes up with,
and whether an edit to the files it was built from is in force or merely saved.
"""
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import prompt_screen                                                    # noqa: E402
import render                                                           # noqa: E402
import server                                                           # noqa: E402


# --- TC1-TC2: the assembled prompt -------------------------------------------------------

def test_the_prompt_is_assembled_in_the_order_start_sh_builds_it():
    got = prompt_screen.assembled("персона", "## Факти\n- один", "естафета")
    assert [p["name"] for p in got["parts"]] == ["persona.md", "факти", "естафета"]
    assert got["text"].index("персона") < got["text"].index("## Факти") \
        < got["text"].index("естафета")
    assert got["chars"] == len(got["text"])
    assert got["parts"][0]["chars"] == len("персона")


def test_a_pending_handoff_is_part_of_the_prompt_and_a_consumed_one_is_not():
    with_note = prompt_screen.assembled("персона", "факти", "естафета")
    without = prompt_screen.assembled("персона", "факти", None)
    assert any(p["name"] == "естафета" for p in with_note["parts"])
    assert all(p["name"] != "естафета" for p in without["parts"])
    assert "естафета" not in without["text"]


def test_the_token_estimate_is_called_an_estimate():
    got = prompt_screen.assembled("я" * 3500, "", None)
    assert 900 < got["tokens"] < 1100           # ~3.5 characters per token, roughly
    html = render.render_prompt(got, [], [], "")
    assert "приблизно" in html or "грубо" in html


# --- TC3: the restart banner -------------------------------------------------------------

def test_a_file_changed_after_the_session_started_needs_a_restart(tmp_path):
    started = time.time() - 100
    old, new = tmp_path / "persona.md", tmp_path / "CLAUDE.md"
    old.write_text("x", encoding="utf-8")
    new.write_text("y", encoding="utf-8")
    import os
    os.utime(old, (started - 500, started - 500))
    names = [f["file"] for f in prompt_screen.stale_files(started, [old, new])]
    assert names == ["CLAUDE.md"]


def test_an_unreadable_file_is_not_reported_as_fresh(tmp_path):
    assert prompt_screen.stale_files(time.time(), [tmp_path / "missing.md"]) == []


def test_the_banner_appears_only_when_something_is_stale():
    quiet = render.render_prompt(prompt_screen.assembled("a", "b", None), [], [], "")
    assert "потрібен перезапуск" not in quiet.lower()
    loud = render.render_prompt(
        prompt_screen.assembled("a", "b", None),
        [{"file": "persona.md", "when": "2026-11-01 09:00", "ago": "20 хв"}], [], "")
    assert "потрібен перезапуск" in loud.lower() and "persona.md" in loud


# --- TC4: the scenarios ------------------------------------------------------------------

SCENARIOS = [
    {"name": "дайджест", "unit": "noos-digest.timer", "cmd": ["status/digest-headless.sh"],
     "prompts": ["status/digest-prompt.md"], "detach": True},
    {"name": "гороскоп", "unit": "noos-mood.timer", "cmd": ["status/mood.py"],
     "prompts": ["status/mood/draft.md", "status/mood/nope.md"],
     "dry": ["status/mood.py", "--dry-run"], "detach": True},
]


def test_a_scenario_row_carries_its_prompts_and_its_schedule():
    rows = prompt_screen.scenario_rows(
        SCENARIOS, {"noos-digest.timer": {"schedules": ["*-*-* 08:03:00"],
                                          "last": "Sat 2026-10-31 20:03:00 EET"}}, ROOT)
    digest = rows[0]
    assert digest["schedules"] == ["*-*-* 08:03:00"]
    assert digest["last"].startswith("Sat")
    assert digest["prompts"][0]["chars"] > 0 and digest["prompts"][0]["exists"]


def test_a_missing_prompt_file_is_named_not_skipped():
    rows = prompt_screen.scenario_rows(SCENARIOS, {}, ROOT)
    mood = rows[1]
    assert [p["file"] for p in mood["prompts"]] == ["status/mood/draft.md",
                                                    "status/mood/nope.md"]
    assert mood["prompts"][1]["exists"] is False
    html = render.render_scenarios(rows, "x", "")
    assert "немає" in html


def test_a_scenario_without_a_dry_run_offers_none():
    rows = prompt_screen.scenario_rows(SCENARIOS, {}, ROOT)
    assert not rows[0]["dry"] and rows[1]["dry"]


# --- TC5-TC6: running one ----------------------------------------------------------------

def test_a_name_the_config_does_not_know_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "run_script", lambda *c, **k: (calls.append(c), (True, ""))[1])
    monkeypatch.setattr(prompt_screen, "scenarios", lambda: SCENARIOS)
    said = server.scenario_action({"action": ["run"], "name": ["; rm -rf ~"]})
    assert "не знаю" in said.lower() and calls == []


def test_a_long_scenario_is_detached_and_a_dry_run_is_not(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "run_script",
                        lambda *c, **k: (calls.append(c), (True, "сказав"))[1])
    monkeypatch.setattr(prompt_screen, "scenarios", lambda: SCENARIOS)

    server.scenario_action({"action": ["run"], "name": ["дайджест"]})
    assert calls[0][0] == "systemd-run"

    calls.clear()
    server.scenario_action({"action": ["dry"], "name": ["гороскоп"]})
    assert calls[0][0] != "systemd-run" and "--dry-run" in calls[0]


def test_a_dry_run_on_a_scenario_that_has_none_is_refused(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "run_script", lambda *c, **k: (calls.append(c), (True, ""))[1])
    monkeypatch.setattr(prompt_screen, "scenarios", lambda: SCENARIOS)
    said = server.scenario_action({"action": ["dry"], "name": ["дайджест"]})
    assert calls == [] and "сухого" in said.lower()


# --- TC7-TC8: the screens ----------------------------------------------------------------

@pytest.mark.parametrize("screen", ["/prompt", "/scenarios"])
def test_the_screens_are_no_longer_placeholders(screen):
    assert screen not in server.SOON


def test_the_prompt_screen_shows_the_files_the_prompt_was_built_from():
    html = render.render_prompt(
        prompt_screen.assembled("персона", "факти", None), [],
        [{"file": "persona.md", "chars": 4000, "dirty": True},
         {"file": "CLAUDE.md", "chars": 30000, "dirty": False}], "")
    assert "persona.md" in html and "CLAUDE.md" in html
    assert "незакомічені" in html


def test_everything_interpolated_is_escaped():
    html = render.render_prompt(
        prompt_screen.assembled("<script>alert(1)</script>", "факти", None), [], [], "")
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_the_prompt_screen_carries_no_env_value():
    """It shows what the session is told, and the session is not told any key."""
    got = prompt_screen.assembled((ROOT / "persona.md").read_text(encoding="utf-8"),
                                  "факти", None)
    html = render.render_prompt(got, [], [], "")
    for name in (".env.voice", "ELEVENLABS_API_KEY", "TELEGRAM_BOT_TOKEN"):
        assert name not in html


# --- t1111: the prompt the session actually has (full review: truth H2, M6, M7, M10) -----

def test_a_consumed_handoff_is_part_of_the_live_prompt(tmp_path):
    """`start.sh` moves handoff.md to handoff-last.md as it reads it, so the file being gone
    is proof the running session carries the note — and the screen read it as proof of the
    opposite, understating the live prompt by 36 %."""
    import os
    f = tmp_path / "handoff-last.md"
    f.write_text("естафета", encoding="utf-8")
    os.utime(f, (9_000.0, 9_000.0))        # archived just before this session came up
    got = prompt_screen.handoff_state(tmp_path, started=10_000.0, now=20_000.0)
    assert got["text"] == "естафета" and got["state"] == "consumed"


def test_a_pending_handoff_is_marked_pending(tmp_path):
    (tmp_path / "handoff.md").write_text("ще не зʼїдена", encoding="utf-8")
    got = prompt_screen.handoff_state(tmp_path, started=10_000.0, now=20_000.0)
    assert got["text"] == "ще не зʼїдена" and got["state"] == "pending"


def test_a_note_consumed_by_a_later_session_than_this_one_is_not_claimed(tmp_path):
    """If the archive is newer than this session's start, it belongs to a session that has
    not started yet — saying nothing beats saying the wrong thing."""
    f = tmp_path / "handoff-last.md"
    f.write_text("чужа", encoding="utf-8")
    import os
    os.utime(f, (30_000.0, 30_000.0))
    got = prompt_screen.handoff_state(tmp_path, started=10_000.0, now=40_000.0)
    assert got["state"] == "unknown" and got["text"] == ""


def test_no_note_at_all_is_its_own_answer(tmp_path):
    got = prompt_screen.handoff_state(tmp_path, started=10_000.0, now=20_000.0)
    assert got["state"] == "none" and got["text"] == ""


def test_the_handoff_carries_the_heading_start_sh_writes(tmp_path):
    """`start.sh` writes «## Естафета з попередньої сесії» before the note; without it the
    pre block is not what the session sees."""
    got = prompt_screen.assembled("персона", "факти", "естафета")
    assert "## Естафета з попередньої сесії" in got["text"]
    assert got["text"].index("факти") < got["text"].index("Естафета")


def test_the_total_matches_what_the_shell_would_build():
    """The claim on this screen is «тут видно те, що бачить сесія», so the arithmetic has to
    be the shell's arithmetic, not an approximation of it."""
    got = prompt_screen.assembled("персона", "## Факти\n- a", "нотатка",
                                  permissions="## Дозволи\n- b")
    shell = ("персона\n## Факти\n- a\n## Дозволи\n- b\n\n"
             "## Естафета з попередньої сесії\nнотатка")
    assert got["text"] == shell
    assert got["chars"] == len(shell)


def test_an_unknown_session_start_is_not_a_claim_that_nothing_changed():
    """M6: the banner's absence reads as «усе актуально». With no start time we do not
    know that, and saying so is the only honest option."""
    html = render.render_prompt(prompt_screen.assembled("a", "b", None), [], [], "",
                                started=0.0)
    assert "не змінювалось" not in html
    assert "невідомо" in html.lower()


def test_a_changed_config_also_asks_for_a_restart(tmp_path):
    """M7: three places promise the banner covers configuration and permissions; it watched
    only persona, CLAUDE.md and the facts."""
    import os
    f = tmp_path / "config.local.json"
    f.write_text("{}", encoding="utf-8")
    os.utime(f, (20_000.0, 20_000.0))
    stale = prompt_screen.stale_files(10_000.0, [f])
    assert [s["file"] for s in stale] == ["config.local.json"]


def test_the_screens_do_not_grow_sys_path(monkeypatch):
    """M10: one entry per GET on /prompt and /rules — the leak t1067 and t1071 fixed
    elsewhere."""
    monkeypatch.setattr(server, "run_script", lambda *a, **k: (True, ""))
    monkeypatch.setattr(server.data, "timer_units", lambda: [])
    server.prompt_html()                      # the first call may import a module
    server.rules_html()
    before = list(sys.path)
    for _ in range(3):
        server.prompt_html()
        server.rules_html()
    assert sys.path == before, "a request must not add an entry"
