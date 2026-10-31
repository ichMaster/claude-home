"""t1053 — the repository is public: personal facts about the owner live in
`config.local.json` (git-ignored), never in a tracked file.

The guard takes the personal values **from the local config at run time** and asserts that
none of them appears in anything git tracks. Nothing personal is written down here, which is
the point: a test that spelled out what it was looking for would publish it again (that is
exactly what the first draft of this file did, and the commit-time review caught it).

This is a narrow regression guard for one task, not a secret scanner — judging what is safe
to publish is a reading, not a regex (CLAUDE.md § Git).
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "config.local.json"

# loaded by file path: `import mood` resolves to status/probes/mood.py once another test
# puts status/probes on sys.path
_spec = importlib.util.spec_from_file_location("noos_mood", ROOT / "status" / "mood.py")
mood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mood)


def test_life_context_default_is_neutral(monkeypatch):
    """TC1: with nothing configured, the prompt gets an instruction, not someone's life."""
    monkeypatch.setattr(mood.astro, "SUBJECT", None)
    monkeypatch.setattr(mood, "conf", lambda key, default=None: default)
    got = mood.life_context()
    assert "загальними побутовими прикладами" in got
    assert len(got) < 120, "a fallback this long is a description, not an instruction"


def test_configured_context_still_used(monkeypatch):
    """TC3: the real value comes from config.local.json and is passed through untouched."""
    monkeypatch.setattr(mood.astro, "SUBJECT", None)
    monkeypatch.setattr(mood, "conf",
                        lambda key, default=None: "справжній контекст"
                        if key == "astro.context" else default)
    assert mood.life_context() == "справжній контекст"


def personal_values():
    """The personal strings worth guarding, read out of the git-ignored local config.

    Short values are skipped: the city alone is already public (the air-raid region and the
    weather city live in the committed config on purpose), and a two-digit number would match
    everywhere. What must never be published is the birth year, the full birth date, the
    coordinates, and any life sketch handed to the forecast prompts.
    """
    astro = json.loads(LOCAL.read_text(encoding="utf-8")).get("astro") or {}
    out = set()
    birth = astro.get("birth") or {}
    if birth.get("date"):
        out.add(str(birth["date"]))
        out.add(str(birth["date"])[:4])          # the year on its own
    for key in ("lat", "lon"):
        if birth.get(key):
            out.add(str(birth[key]))
    if astro.get("context"):
        out.add(str(astro["context"]))
    for subject in (astro.get("subjects") or {}).values():
        if isinstance(subject, dict) and subject.get("context"):
            out.add(str(subject["context"]))
    return {v for v in out if len(v) >= 4}


def test_no_tracked_file_carries_a_personal_value():
    """TC2: regression — nothing from the personal config appears in anything git tracks."""
    if not LOCAL.is_file():
        pytest.skip("немає config.local.json — нічого звіряти")
    values = personal_values()
    assert values, "config.local.json has no personal values — did its shape change?"

    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                           capture_output=True, text=True).stdout.split("\0")
    hits = []
    for name in filter(None, files):
        f = ROOT / name
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [name for v in values if v in text]
    assert not hits, "personal values from config.local.json in tracked files: " + \
                     ", ".join(sorted(set(hits)))
