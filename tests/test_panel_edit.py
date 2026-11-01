"""t1102 — panel, phase 10a: configuration as a form.

Writes go to `config.local.json` and nowhere else, through the versioned atomic path, so a
wrong value is one `tools/versions.py restore` away. The tests that matter most are the
refusals: what the form must not be able to touch.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import render                                                           # noqa: E402
import rules_screen                                                     # noqa: E402
import server                                                           # noqa: E402

DEFAULT = {"probes": {"loe": {"queue": "4.1", "ttl": 600, "on": True, "share": 0.5}},
           "panel": {"port": 8091, "probes": ["loe", "alarm"]},
           "astro": {"birth": {"place": "десь"}},
           "permissions": {"mail.send": "ask"}}


@pytest.fixture
def local(tmp_path, monkeypatch):
    f = tmp_path / "config.local.json"
    f.write_text(json.dumps({"probes": {"loe": {"queue": "3.2"}}}, ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(rules_screen, "LOCAL", f)
    monkeypatch.setattr(rules_screen, "_default_config", lambda: DEFAULT)
    monkeypatch.setattr(rules_screen, "masked_keys", lambda: ["astro.birth"])
    return f


def saved(f):
    return json.loads(f.read_text(encoding="utf-8"))


# --- TC1: the write ----------------------------------------------------------------------

@pytest.mark.parametrize("key,raw,want", [
    ("probes.loe.ttl", "900", 900),
    ("probes.loe.queue", "5.2", "5.2"),
    ("probes.loe.on", "off", False),
    ("probes.loe.share", "0.75", 0.75),
    ("panel.port", "9000", 9000),
])
def test_a_setting_keeps_the_type_of_its_default(local, key, raw, want):
    ok, said = rules_screen.set_setting(key, raw)
    assert ok, said
    node = saved(local)
    for part in key.split(".")[:-1]:
        node = node[part]
    assert node[key.split(".")[-1]] == want and isinstance(
        node[key.split(".")[-1]], type(want))


def test_the_committed_defaults_are_never_touched(local):
    before = (ROOT / "config.json").read_text(encoding="utf-8")
    rules_screen.set_setting("probes.loe.ttl", "900")
    assert (ROOT / "config.json").read_text(encoding="utf-8") == before


# --- TC2: back to default ----------------------------------------------------------------

def test_resetting_removes_the_override_rather_than_writing_the_default(local):
    ok, _ = rules_screen.reset_setting("probes.loe.queue")
    assert ok
    assert "loe" not in saved(local).get("probes", {}), \
        "an emptied parent block must be pruned, not left as {}"


def test_resetting_what_has_no_override_says_so(local):
    ok, said = rules_screen.reset_setting("probes.loe.ttl")
    assert not ok and "немає" in said.lower()


# --- TC3-TC6: the refusals ---------------------------------------------------------------

@pytest.mark.parametrize("key,raw", [
    ("astro.birth.place", "інше"),             # masked: terminal only
    ("panel.probes", "[]"),                    # a list has its own screen
    ("probes.loe", "{}"),                      # a block is not a form field
    ("permissions.mail.send", "free"),         # permissions are set from the terminal
    ("probes.loe.nope", "1"),                  # the form cannot invent a setting
    ("", "1"),
    ("../../etc/passwd", "1"),
])
def test_what_the_form_may_not_touch(local, key, raw):
    before = saved(local)
    ok, said = rules_screen.set_setting(key, raw)
    assert not ok and said
    assert saved(local) == before, "a refusal must write nothing"


@pytest.mark.parametrize("raw", ["багато", "", "9e999999", "0x10"])
def test_a_value_that_will_not_parse_is_refused(local, raw):
    ok, said = rules_screen.set_setting("probes.loe.ttl", raw)
    assert not ok and saved(local) == {"probes": {"loe": {"queue": "3.2"}}}


@pytest.mark.parametrize("raw,want", [("on", True), ("off", False), ("так", True),
                                      ("ні", False), ("1", True), ("0", False)])
def test_a_flag_understands_both_languages(local, raw, want):
    ok, _ = rules_screen.set_setting("probes.loe.on", raw)
    assert ok and saved(local)["probes"]["loe"]["on"] is want


# --- TC5: versions -----------------------------------------------------------------------

def test_every_write_takes_a_version_first(local, monkeypatch):
    kept = []
    monkeypatch.setattr(rules_screen, "atomic_write_text",
                        lambda target, text: (kept.append(Path(target).name),
                                              Path(target).write_text(text,
                                                                     encoding="utf-8")))
    rules_screen.set_setting("probes.loe.ttl", "900")
    assert kept == ["config.local.json"], \
        "the write must go through the versioned atomic path, not write_text"


# --- the form itself ---------------------------------------------------------------------

def test_an_editable_row_gets_a_field_and_a_masked_one_does_not():
    rows = rules_screen.setting_rows(DEFAULT, {"probes": {"loe": {"queue": "3.2"}}},
                                     ["astro.birth"])
    html = render.render_rules(rows, rules_screen.permissions("", [], {}), [], [],
                               "", "", token="tok")
    assert 'name="value"' in html
    masked = [r for r in rows if r["key"] == "astro.birth.place"][0]
    assert not masked["editable"]
    block = html.split("astro.birth.place")[1].split("</tr>")[0]
    assert 'name="value"' not in block


def test_the_permissions_section_shows_the_real_levels():
    perms = rules_screen.permissions("--permission-mode auto", [], {},
                                     levels={"mail.send": "ask"})
    html = render.render_rules([], perms, [], [], "", "", token="tok")
    assert "mail.send" in html
    assert "термінал" in html, "the screen must say where permissions are set"
    assert 'name="permission"' not in html, "no switch: the owner's rule is terminal only"


# --- the action --------------------------------------------------------------------------

def test_the_action_routes_save_and_reset(monkeypatch):
    calls = []
    monkeypatch.setattr(rules_screen, "set_setting",
                        lambda k, v: (calls.append(("set", k, v)), (True, "ok"))[1])
    monkeypatch.setattr(rules_screen, "reset_setting",
                        lambda k: (calls.append(("reset", k)), (True, "ok"))[1])
    server.rules_action({"action": ["save"], "key": ["probes.loe.ttl"], "value": ["900"]})
    server.rules_action({"action": ["reset"], "key": ["probes.loe.ttl"]})
    assert calls == [("set", "probes.loe.ttl", "900"), ("reset", "probes.loe.ttl")]


def test_an_unknown_action_does_nothing(monkeypatch):
    monkeypatch.setattr(rules_screen, "set_setting",
                        lambda k, v: pytest.fail("must not be called"))
    assert "невідом" in server.rules_action({"action": ["drop"], "key": ["x"]}).lower()


# --- t1105: reset had none of save's guards (full review: writes M1, security H2) --------
# «Повернути типове» is rendered only on editable rows, but a crafted POST with a live form
# token reached `reset_setting` directly — and it deleted the birth data, the 603-channel
# list and the whole permissions block, the two writes the design says can never come from
# a page.

@pytest.mark.parametrize("key", ["astro.birth.place", "astro.birth", "astro",
                                 "probes.youtube.channels", "permissions",
                                 "permissions.mail.send", "user.name"])
def test_reset_refuses_exactly_what_save_refuses(tmp_path, monkeypatch, key):
    f = tmp_path / "config.local.json"
    before = {"astro": {"birth": {"place": "десь", "lat": 1.0}, "context": "життя"},
              "probes": {"youtube": {"channels": [{"name": "a"}]}},
              "permissions": {"mail.send": "free"},
              "user": {"name": "хтось"}}
    f.write_text(json.dumps(before, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rules_screen, "LOCAL", f)
    monkeypatch.setattr(rules_screen, "_default_config", lambda: DEFAULT)
    monkeypatch.setattr(rules_screen, "masked_keys", lambda: ["astro.birth", "astro.context",
                                                              "user"])
    ok, said = rules_screen.reset_setting(key)
    assert not ok and said
    assert json.loads(f.read_text(encoding="utf-8")) == before, "a refusal writes nothing"


def test_reset_still_works_on_an_ordinary_setting(local):
    ok, said = rules_screen.reset_setting("probes.loe.queue")
    assert ok and "probes" not in saved(local)


def test_reset_refuses_a_parent_that_holds_more_than_the_key(tmp_path, monkeypatch):
    """`key=astro` wiped fourteen leaves in one press. A reset is for one setting."""
    f = tmp_path / "config.local.json"
    f.write_text(json.dumps({"probes": {"loe": {"queue": "3.2", "ttl": 900}}}),
                 encoding="utf-8")
    monkeypatch.setattr(rules_screen, "LOCAL", f)
    monkeypatch.setattr(rules_screen, "_default_config", lambda: DEFAULT)
    monkeypatch.setattr(rules_screen, "masked_keys", lambda: [])
    ok, said = rules_screen.reset_setting("probes.loe")
    assert not ok and "блок" in said.lower()
    assert json.loads(f.read_text(encoding="utf-8")) == {
        "probes": {"loe": {"queue": "3.2", "ttl": 900}}}
