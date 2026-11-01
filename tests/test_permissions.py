"""t1102 — permissions that bind: a block in config, rendered into the system prompt.

Phase 8's honest finding was that nothing machine-readable governed this assistant. These
tests are about the one property that makes the new block different from decoration: it
reaches the prompt, and it cannot be loosened by accident.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import permissions                                                     # noqa: E402


def test_every_decision_is_rendered_with_its_level():
    text = permissions.prompt_block({"mail.send": "ask", "files.delete": "never"})
    assert "ask" in text or "з підтвердженням" in text
    assert "mail.send" in text and "files.delete" in text


def test_a_hard_rule_says_it_is_not_negotiable():
    text = permissions.prompt_block({})
    for key in permissions.HARD:
        assert key in text
    assert "не обговорюється" in text


@pytest.mark.parametrize("level", ["", "yes", "FREE ", "можна", None])
def test_an_unknown_level_reads_as_never_not_as_free(level):
    """A corrupt or hand-edited value must fail closed: the safe reading of a level nobody
    recognises is "do not"."""
    assert permissions.level("mail.send", {"mail.send": level}) == "never"


def test_a_known_level_is_kept():
    assert permissions.level("mail.send", {"mail.send": "free"}) == "free"


def test_an_absent_decision_falls_back_to_its_default():
    assert permissions.level("mail.send", {}) == permissions.DECISIONS["mail.send"]["default"]


def test_setting_a_level_writes_it(tmp_path, monkeypatch):
    target = tmp_path / "config.local.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(permissions, "LOCAL", target)
    assert permissions.set_level("mail.send", "free")
    got = json.loads(target.read_text(encoding="utf-8"))
    assert got["permissions"]["mail.send"] == "free"


@pytest.mark.parametrize("key,level", [("mail.send", "sometimes"), ("nope.key", "free"),
                                       ("", "free"), ("mail.send", "")])
def test_an_unknown_key_or_level_is_refused(tmp_path, monkeypatch, key, level):
    target = tmp_path / "config.local.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(permissions, "LOCAL", target)
    assert permissions.set_level(key, level) is False
    assert json.loads(target.read_text(encoding="utf-8")) == {}


def test_a_hard_rule_cannot_be_lowered(tmp_path, monkeypatch):
    target = tmp_path / "config.local.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(permissions, "LOCAL", target)
    for key in permissions.HARD:
        assert permissions.set_level(key, "free") is False
    assert json.loads(target.read_text(encoding="utf-8")) == {}


def test_the_block_reaches_the_assembled_prompt():
    sys.path.insert(0, str(ROOT / "panel"))
    import prompt_screen
    got = prompt_screen.assembled("персона", "факти", None,
                                  permissions=permissions.prompt_block({}))
    assert any(p["name"] == "дозволи" for p in got["parts"])
    assert "не обговорюється" in got["text"]


def test_start_sh_appends_the_block_to_the_prompt():
    """The one property that separates this from decoration: the session is actually told."""
    start = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "permissions.py" in start and "prompt" in start


# --- t1112: a malformed level must fail closed, not raise (full review: writes M4) -------

@pytest.mark.parametrize("value", [["free"], {"level": "free"}, 3.5, b"free"])
def test_an_unhashable_or_odd_level_reads_as_never(value):
    """`x in dict` needs a hashable x, so a JSON array or object raised — and all three
    readers caught the exception, which meant the whole permission block vanished from the
    system prompt in silence."""
    assert permissions.level("mail.send", {"mail.send": value}) == "never"


@pytest.mark.parametrize("blob", ["free", ["free"], 7, None])
def test_a_permissions_node_that_is_not_a_block_does_not_raise(blob, monkeypatch):
    monkeypatch.setattr(permissions, "conf", lambda key, default=None:
                        blob if key == "permissions" else default)
    assert permissions.levels() == {}
    text = permissions.prompt_block()
    assert "не обговорюється" in text, "the block must still be rendered"
