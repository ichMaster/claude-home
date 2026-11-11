"""t1140 — the v2 scaffold must be unable to touch v1.

Phase 0 of docs/astro-v2-reference.md. There is no content in v2 yet; what these tests guard
is the plumbing, because every way this could go wrong is irreversible: a run that appends to
v1's log, a silent fallback to v1's paths when the configuration is missing, a second
ephemeris that makes the two readings incomparable, or an empty prompt read as an instruction.
"""
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

import mood2
import mood
import astro

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 11, 11)

V1_FILES = ["status/state/mood.log", "status/state/mood.json",
            "status/state/forecast-claims.jsonl"]


def _digests():
    """What every v1 state file looks like right now — missing ones included, so a v2 run
    that *creates* one is caught as surely as one that appends."""
    out = {}
    for rel in V1_FILES:
        f = ROOT / rel
        out[rel] = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else None
    return out


# A reference day small enough to reason about: one loud window, no void, no natal hit — so
# the fidelity counts in check_items have exactly one thing to agree about.
FAKE_REFERENCE = ("Пн 3мар с 10:00 до 12:00\n"
                  "✤✤✤ Влияет Сатурн в 7 доме. Якесь трактування. (☽9°♍△♄9°♉)\n")
FAKE_ITEMS = [{"id": "p1", "kind": "window", "from": "10:00", "to": "12:00", "weight": 3,
               "bodies": "Сатурн", "house": "7", "formula": "(☽9°♍△♄9°♉)",
               "meaning": "Якесь трактування.", "natal": None, "span": None}]


def canned(stage, prompt):
    """What each stage would answer, in the shape the next stage requires."""
    if stage == "read":
        return json.dumps(FAKE_ITEMS, ensure_ascii=False)
    if stage == "pick":
        return json.dumps({"ids": ["p1"], "frame": "p1", "order": "одне вікно",
                           "drop": "нічого"}, ensure_ascii=False)
    return ("ДЕНЬ\nДоба одного вікна. [p1]\n\n"
            "ПРОГНОЗ\nзранку | тягне тиснути й доводити своє [p1]\n\n"
            "ДІЯ\nНе плутай впертість із правотою. [p1]\n\n"
            "ОСНОВА\np1 10:00-12:00 ✤✤✤ (☽9°♍△♄9°♉)\n")


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """A v2 whose own paths live in tmp_path and whose model calls are canned."""
    calls = []

    def fake_call(stage, prompt):
        calls.append((stage, prompt))
        return canned(stage, prompt)

    monkeypatch.setattr(mood2, "call", fake_call)
    monkeypatch.setattr(mood2, "state_path",
                        lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(mood2, "reference_text", lambda day: FAKE_REFERENCE)
    return calls, tmp_path


# --- TC1, TC2: v1 is untouchable -----------------------------------------------------------

def test_dry_run_writes_nothing(staged):
    """TC1 — the whole pipeline, no state of its own written, nothing sent."""
    calls, tmp = staged
    before = _digests()
    parts = mood2.run(DAY, dry_run=True)
    assert [c[0] for c in calls] == mood2.stages()
    assert list(parts) == mood2.stages()
    assert not list(tmp.iterdir()), "dry run wrote files"
    assert _digests() == before


def test_run_writes_only_its_own_paths(staged):
    """TC2 — a real run leaves every v1 state file byte-identical."""
    calls, tmp = staged
    before = _digests()
    mood2.run(DAY)
    assert _digests() == before
    written = sorted(p.name for p in tmp.iterdir())
    assert written == ["astro2-log", "astro2-state"]
    state = json.loads((tmp / "astro2-state").read_text())
    assert state["day"] == DAY.isoformat()
    assert state["stages"]["day"].startswith("ДЕНЬ")
    assert state["reading"] == state["stages"]["day"], "the state keeps the markers"


def test_configured_paths_are_separate_and_named():
    """TC2 — the configured paths themselves live apart from v1's, and say so in the name."""
    for key in ("log", "state", "claims"):
        p = mood2.state_path(key)
        assert "status/state" in p.as_posix()
        assert "v2" in p.name, f"{key}: {p.name} does not say which version wrote it"
        assert p != mood.state_path(key)
    assert mood2.claims_file() != mood.claims_file()


# --- TC3: no silent prompt ------------------------------------------------------------------

def test_missing_prompt_names_the_file(monkeypatch, tmp_path):
    """TC3 — a stage with no prompt file is an error naming the path it looked for."""
    monkeypatch.setattr(mood2, "prompts_dir", lambda: tmp_path)
    with pytest.raises(mood2.MissingPrompt) as e:
        mood2.prompt_text("read")
    assert str(tmp_path / "read.md") in str(e.value)


def test_every_configured_stage_has_a_prompt():
    for stage in mood2.stages():
        assert mood2.prompt_text(stage).strip(), f"{stage}: empty prompt"


def test_placeholders_block_sending(monkeypatch, tmp_path):
    """A stub prompt must never be able to speak, whatever phase the work is in.

    Phase 1 filled every prompt (t1143), so the guard is exercised against a stub made for
    the test rather than against the real directory — the mechanism is what matters, and it
    is what the next phase will lean on again.
    """
    sent = []
    monkeypatch.setattr(mood, "send", lambda text, role="mood": sent.append(text))
    monkeypatch.setattr(mood2, "prompts_dir", lambda: tmp_path)
    for stage in mood2.stages():
        (tmp_path / f"{stage}.md").write_text("справжній промпт", encoding="utf-8")
    (tmp_path / "day.md").write_text(f"{mood2.PLACEHOLDER_MARK}. Ще не написано.",
                                     encoding="utf-8")
    assert "day" in mood2.placeholders()
    with pytest.raises(mood2.NotReady):
        mood2.send("читання")
    assert sent == []


def test_filled_prompt_substitutes_every_variable(monkeypatch, tmp_path):
    monkeypatch.setattr(mood2, "prompts_dir", lambda: tmp_path)
    (tmp_path / "read.md").write_text("дата {{ДАТА}}, факти {{ФАКТИ}}, еталон {{ЕТАЛОН}}")
    got = mood2.fill("read", ДАТА="2026-11-11", ФАКТИ="Ф", ЕТАЛОН="Е")
    assert got == "дата 2026-11-11, факти Ф, еталон Е"
    assert "{{" not in got


# --- TC4: one ephemeris ---------------------------------------------------------------------

def test_facts_come_from_the_same_ephemeris():
    """TC4 — v2's fact text is v1's, for a fixed date, to the byte."""
    assert mood2.fact_text(DAY) == mood.fact_lines(astro.facts(DAY))


def test_v2_has_no_ephemeris_of_its_own():
    """The same rule, structurally: a second sky would be a second source of truth."""
    src = (ROOT / "status" / "mood2.py").read_text()
    assert "swisseph" not in src and "import swe" not in src
    assert "import astro" in src


# --- TC5: no fallback -----------------------------------------------------------------------

def test_refuses_without_its_config_block(monkeypatch):
    """TC5 — unconfigured means stop, not «write where v1 writes»."""
    monkeypatch.setattr(mood2, "conf", lambda key, default=None: None)
    for call in (mood2.require_config, mood2.stages, mood2.claims_file,
                 lambda: mood2.run(DAY)):
        with pytest.raises(mood2.Unconfigured):
            call()


def test_empty_config_block_is_also_a_refusal(monkeypatch):
    monkeypatch.setattr(mood2, "conf", lambda key, default=None: {} if key == "astro2" else default)
    with pytest.raises(mood2.Unconfigured):
        mood2.require_config()


# --- TC6: the record stays honest -----------------------------------------------------------

def test_as_is_document_names_every_v1_prompt():
    """TC6 — the v1 record cannot quietly go stale on a prompt it never mentioned."""
    doc = (ROOT / "docs" / "astro-v1-asis.md").read_text()
    missing = [p.name for p in sorted((ROOT / "status" / "mood").glob("*.md"))
               if p.name not in doc]
    assert not missing, f"not named in docs/astro-v1-asis.md: {missing}"


# --- the entry point itself ------------------------------------------------------------------

def test_cli_facts_needs_no_model():
    """`--facts` is the one path a person can run without paying for a call."""
    out = subprocess.run([sys.executable, str(ROOT / "status" / "mood2.py"), "--facts",
                          "--day", DAY.isoformat()],
                         capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip(), "no facts printed"


def test_cli_send_refuses_while_any_prompt_is_a_stub(monkeypatch, tmp_path, capsys):
    """`--send` exits 2 and delivers nothing rather than speaking a stub out loud."""
    sent = []
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    for stage in mood2.stages():
        (prompts / f"{stage}.md").write_text("справжній промпт", encoding="utf-8")
    (prompts / "day.md").write_text(f"{mood2.PLACEHOLDER_MARK}. Ще не написано.",
                                    encoding="utf-8")
    monkeypatch.setattr(mood2, "prompts_dir", lambda: prompts)
    monkeypatch.setattr(mood2, "call", canned)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(mood2, "reference_text", lambda day: FAKE_REFERENCE)
    monkeypatch.setattr(mood, "send", lambda text, role="mood": sent.append(text))
    monkeypatch.setattr(sys, "argv", ["mood2.py", "--day", DAY.isoformat(), "--send"])
    assert mood2.main() == 2
    assert sent == []
    assert "t1143" in capsys.readouterr().err


def test_cli_send_delivers_once_the_prompts_are_real(monkeypatch, tmp_path):
    """And the other half: with phase 1 finished, --send actually speaks (t1143)."""
    sent = []
    monkeypatch.setattr(mood2, "call", canned)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(mood2, "reference_text", lambda day: FAKE_REFERENCE)
    monkeypatch.setattr(mood, "send", lambda text, role="mood": sent.append(text))
    monkeypatch.setattr(sys, "argv", ["mood2.py", "--day", DAY.isoformat(), "--send"])
    assert mood2.main() == 0
    assert len(sent) == 1 and "[p1]" not in sent[0], "the audit markers are not for the ear"


# --- a stage that dies says so ----------------------------------------------------------------

def test_timed_out_stage_names_itself(monkeypatch):
    """A placeholder prompt hit the 420 s call ceiling on the first real run and the entry
    point answered with a raw TimeoutExpired traceback. The stage has to name itself."""
    def boom(prompt, model="", timeout=0):
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=timeout)

    monkeypatch.setattr(mood, "run_claude", boom)
    with pytest.raises(mood2.StageFailed) as e:
        mood2.call("day", "промпт")
    assert "day" in str(e.value) and "420" in str(e.value)


def test_failed_stage_exits_three_and_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mood2, "reference_text", lambda day: FAKE_REFERENCE)
    monkeypatch.setattr(mood2, "state_path", lambda key: tmp_path / f"astro2-{key}")
    monkeypatch.setattr(mood2, "call",
                        lambda stage, prompt: (_ for _ in ()).throw(
                            mood2.StageFailed(f"стадія «{stage}» не відповіла за 420 с")))
    monkeypatch.setattr(sys, "argv", ["mood2.py", "--day", DAY.isoformat()])
    assert mood2.main() == 3
    assert not list(tmp_path.iterdir())
    assert "read" in capsys.readouterr().err
