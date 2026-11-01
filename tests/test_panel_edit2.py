"""t1103 — panel, phase 10b: the file editors and the timer times.

The two most destructive writes in the project. `persona.md` is who I am; a malformed
`OnCalendar` makes a timer stop existing quietly. So most of these tests are about the
guards, and one is about the panel undoing its own damage without a human.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import prompt_screen                                                    # noqa: E402
import render                                                           # noqa: E402
import rules_screen                                                     # noqa: E402
import server                                                           # noqa: E402

UNIT = """[Unit]
Description=Ноос: дайджест зранку і ввечері

[Timer]
OnCalendar=*-*-* 08:03:00
OnCalendar=*-*-* 20:03:00
Persistent=true

[Install]
WantedBy=timers.target
"""


# --- TC1-TC3: the editors ----------------------------------------------------------------

@pytest.fixture
def files(tmp_path, monkeypatch):
    persona = tmp_path / "persona.md"
    persona.write_text("я" * 1000, encoding="utf-8")
    monkeypatch.setattr(prompt_screen, "HOME", tmp_path)
    monkeypatch.setattr(prompt_screen, "EDITABLE", {"persona.md", "CLAUDE.md"})
    return tmp_path


def test_a_save_writes_what_was_submitted(files):
    ok, said = prompt_screen.save_file("persona.md", "я" * 1000 + " і ще трохи")
    assert ok, said
    assert (files / "persona.md").read_text(encoding="utf-8").endswith("і ще трохи")


def test_the_save_goes_through_the_versioned_path(files, monkeypatch):
    seen = []
    monkeypatch.setattr(prompt_screen, "atomic_write_text",
                        lambda t, text: (seen.append(Path(t).name),
                                         Path(t).write_text(text, encoding="utf-8")))
    prompt_screen.save_file("persona.md", "я" * 1200)
    assert seen == ["persona.md"]


@pytest.mark.parametrize("name,text", [
    ("persona.md", ""), ("persona.md", "   \n\t "),
    ("CLAUDE.md", "x" * 100),                     # on the list, but absent from disk
    ("../.env.voice", "x" * 1000),
    ("notes.md", "x" * 1000),
    ("", "x" * 1000),
])
def test_what_a_save_refuses(files, name, text):
    before = (files / "persona.md").read_text(encoding="utf-8")
    ok, said = prompt_screen.save_file(name, text)
    assert not ok and said, "a file that is absent is not created by an editor either"
    assert (files / "persona.md").read_text(encoding="utf-8") == before


def test_halving_a_file_needs_a_second_press(files):
    ok, said = prompt_screen.save_file("persona.md", "я" * 400)
    assert not ok and "підтверд" in said.lower()
    assert len((files / "persona.md").read_text(encoding="utf-8")) == 1000
    ok, said = prompt_screen.save_file("persona.md", "я" * 400, confirm=True)
    assert ok and len((files / "persona.md").read_text(encoding="utf-8")) == 400


def test_growing_a_file_needs_no_confirmation(files):
    ok, _ = prompt_screen.save_file("persona.md", "я" * 5000)
    assert ok


# --- TC4-TC5: rewriting a unit -----------------------------------------------------------

def test_the_calendar_lines_are_replaced_in_place_and_nothing_else_changes():
    got = rules_screen.replace_calendar(UNIT, ["*-*-* 09:00:00"])
    assert got.count("OnCalendar=") == 1 and "OnCalendar=*-*-* 09:00:00" in got
    assert "Persistent=true" in got and "WantedBy=timers.target" in got
    lines = got.splitlines()
    assert lines.index("OnCalendar=*-*-* 09:00:00") == 4, "the new line takes the old place"


def test_several_lines_can_replace_one():
    got = rules_screen.replace_calendar(
        "[Timer]\nOnCalendar=*-*-* 08:00:00\nPersistent=true\n",
        ["*-*-* 08:00:00", "*-*-* 20:00:00"])
    assert got.splitlines() == ["[Timer]", "OnCalendar=*-*-* 08:00:00",
                                "OnCalendar=*-*-* 20:00:00", "Persistent=true"]


def test_a_unit_without_a_calendar_line_is_not_rewritten():
    with pytest.raises(ValueError):
        rules_screen.replace_calendar("[Timer]\nOnUnitActiveSec=15min\n", ["*-*-* 09:00:00"])


# --- TC6-TC8: the action -----------------------------------------------------------------

@pytest.fixture
def unit_file(tmp_path, monkeypatch):
    f = tmp_path / "noos-digest.timer"
    f.write_text(UNIT, encoding="utf-8")
    monkeypatch.setattr(server, "UNIT_DIR", tmp_path)
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-digest.timer"])
    return f


def runner(monkeypatch, *, valid=True, loads=True):
    calls = []

    def fake(*cmd, **kwargs):
        calls.append(cmd)
        if "systemd-analyze" in cmd[0]:
            return (valid, "" if valid else "Failed to parse calendar: Invalid argument")
        if cmd[0] == "systemctl" and "show" in cmd:
            return True, f"LoadState={'loaded' if loads else 'error'}"
        return True, ""
    monkeypatch.setattr(server, "run_script", fake)
    return calls


def test_an_invalid_spec_is_refused_before_the_write(unit_file, monkeypatch):
    calls = runner(monkeypatch, valid=False)
    said = server.schedule_action({"unit": ["noos-digest.timer"],
                                   "calendar": ["щось не те"]})
    assert "не приймає" in said or "Invalid" in said
    assert unit_file.read_text(encoding="utf-8") == UNIT
    assert all("daemon-reload" not in " ".join(c) for c in calls)


def test_a_unit_systemd_did_not_name_never_reaches_a_command(unit_file, monkeypatch):
    calls = runner(monkeypatch)
    said = server.schedule_action({"unit": ["ssh-agent.service"],
                                   "calendar": ["*-*-* 09:00:00"]})
    assert "не знаю" in said.lower() and calls == []


def test_a_good_spec_is_written_and_reloaded(unit_file, monkeypatch):
    calls = runner(monkeypatch)
    said = server.schedule_action({"unit": ["noos-digest.timer"],
                                   "calendar": ["*-*-* 09:00:00\n*-*-* 21:00:00"]})
    body = unit_file.read_text(encoding="utf-8")
    assert "09:00:00" in body and "21:00:00" in body and "08:03" not in body
    assert any("daemon-reload" in " ".join(c) for c in calls)
    assert "09:00:00" in said


def test_a_unit_that_stops_loading_is_put_back_without_a_human(unit_file, monkeypatch):
    """A panel that can break a timer must be able to undo it by itself."""
    calls = runner(monkeypatch, loads=False)
    said = server.schedule_action({"unit": ["noos-digest.timer"],
                                   "calendar": ["*-*-* 09:00:00"]})
    assert unit_file.read_text(encoding="utf-8") == UNIT, "the old unit must be restored"
    assert "поверну" in said.lower() or "відкочено" in said.lower()
    assert sum("daemon-reload" in " ".join(c) for c in calls) == 2


def test_the_editor_and_the_schedule_field_are_rendered():
    html = render.render_prompt(prompt_screen.assembled("a", "b", None), [],
                                [{"file": "persona.md", "chars": 10, "dirty": False,
                                  "text": "текст", "exists": True}], "", token="tok")
    assert "<textarea" in html and 'name="file"' in html
    rows = rules_screen.schedule_rows([("noos-digest.timer",
                                        "TimersCalendar={ OnCalendar=*-*-* 08:03:00 }\n",
                                        "")])
    sched = render.render_rules([], rules_screen.permissions("", [], {}), rows, [],
                                "", "", token="tok")
    assert 'name="calendar"' in sched


# --- t1106: the field could not express two times (full review: writes H3, M3) -----------

def specs_of(value):
    return server.schedule_specs(value)


def test_the_separator_is_the_one_the_form_produces():
    """The field is a single-line input prefilled with «; », and the action split on «,» —
    systemd's own separator *inside* one spec. So the three timers with two or more times
    could never be edited, and `Mon,Tue *-*-* 09:00:00` was silently written as two
    different schedules."""
    assert specs_of("*-*-* 08:03:00; *-*-* 20:03:00") == ["*-*-* 08:03:00",
                                                          "*-*-* 20:03:00"]
    assert specs_of("*-*-* 08:03:00\n*-*-* 20:03:00") == ["*-*-* 08:03:00",
                                                          "*-*-* 20:03:00"]


def test_a_comma_belongs_to_systemd_and_is_left_alone():
    assert specs_of("Mon,Tue *-*-* 09:00:00") == ["Mon,Tue *-*-* 09:00:00"]
    assert specs_of("*-*-* 09,11,13:05:00") == ["*-*-* 09,11,13:05:00"]


def test_the_prefill_round_trips():
    """What the form offers must be submittable unchanged — the digest's own schedule was
    not."""
    # `schedule_rows` reads `systemctl show` output, not the unit file
    show = ("TimersCalendar={ OnCalendar=*-*-* 08:03:00 ; next_elapse=… }\n"
            "TimersCalendar={ OnCalendar=*-*-* 20:03:00 ; next_elapse=… }\n")
    rows = rules_screen.schedule_rows([("noos-digest.timer", show, "")])
    prefill = render.schedule_prefill(rows[0]["calendars"])
    assert specs_of(prefill) == ["*-*-* 08:03:00", "*-*-* 20:03:00"]


def test_an_interval_line_is_not_offered_as_a_calendar_spec():
    rows = rules_screen.schedule_rows([(
        "noos-watch.timer",
        "TimersMonotonic={ OnUnitActiveUSec=15min ; next_elapse=1h }\n", "")])
    html = render.render_rules([], rules_screen.permissions("", [], {}), rows, [],
                               "", "", token="tok")
    assert 'name="calendar"' not in html, "an interval timer has no OnCalendar to edit"


def test_a_failed_daemon_reload_is_not_reported_as_success(unit_file, monkeypatch):
    """M3: the reload's result was discarded, and `LoadState` still answers «loaded» for the
    old unit systemd holds in memory — so the file and the running timer disagreed while the
    screen said it worked."""
    calls = []

    def fake(*cmd, **kwargs):
        calls.append(cmd)
        if "systemd-analyze" in cmd[0]:
            return True, ""
        if "daemon-reload" in cmd:
            return False, "Failed to reload daemon"
        if cmd[0] == "systemctl" and "show" in cmd:
            return True, "LoadState=loaded"
        return True, ""
    monkeypatch.setattr(server, "run_script", fake)
    said = server.schedule_action({"unit": ["noos-digest.timer"],
                                   "calendar": ["*-*-* 09:00:00"]})
    assert "не перезавантаж" in said.lower() or "daemon-reload" in said
    assert unit_file.read_text(encoding="utf-8") == UNIT, "and the unit is put back"
