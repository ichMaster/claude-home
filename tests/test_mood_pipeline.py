"""t1051 — forecast pipeline regressions: yesterday's context after --resume, partial
persistence when a stage dies, and no owner-portrait leak into another subject's chart."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

# loaded by file path: `import mood` resolves to status/probes/mood.py once another test
# puts status/probes on sys.path
ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("noos_mood", ROOT / "status" / "mood.py")
mood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mood)


LOG = """\
===== 2026-10-30 =====

--- підсумок ---
ПІДСУМОК: старий текст дня.

===== 2026-10-30 =====

--- підсумок (перероблено) ---
ПІДСУМОК: перероблений текст дня.
"""


def test_yesterday_block_sees_resumed_summary(monkeypatch, tmp_path):
    """TC1: the morning after a --resume run, yesterday's (reworked) summary is found."""
    log = tmp_path / "mood.log"
    log.write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(mood, "state_path", lambda key: log)
    block = mood.yesterday_block(date(2026, 10, 31))
    assert "перероблений текст дня" in block


def test_write_forecast_failure_keeps_draft(monkeypatch):
    """TC2: the review call dies — the already-written draft survives in `partial`."""
    calls = []

    def fake_run(prompt, model="", timeout=0):
        calls.append(prompt)
        if len(calls) == 1:
            return "ЧИТАННЯ: довгий черновик дня"
        raise RuntimeError("виклик не вдався")

    monkeypatch.setattr(mood, "run_claude", fake_run)
    monkeypatch.setattr(mood, "yesterday_block", lambda d: "")
    monkeypatch.setattr(mood, "calibration", lambda: "")
    monkeypatch.setattr(mood, "life_context", lambda: "")
    monkeypatch.setattr(mood, "reference_block", lambda d: "")
    monkeypatch.setattr(mood.astro, "day_focus", lambda d: {})
    monkeypatch.setattr(mood.astro, "focus_lines", lambda f, d: "")
    monkeypatch.setattr(mood.astro, "glossary_lines", lambda: "")
    rank = {"main": [], "background": [], "tender": [], "why": "", "raw": ""}
    partial = {}
    with pytest.raises(RuntimeError):
        mood.write_forecast("НАТАЛ", date(2026, 10, 31), [], rank, partial=partial)
    assert "черновик" in partial and "довгий черновик дня" in partial["черновик"]


def test_subject_never_inherits_owner_portrait(monkeypatch, tmp_path):
    """TC3: a subject with no natal_file of their own gets the computed chart only."""
    portrait = tmp_path / "natal.md"
    portrait.write_text("# портрет\nВласник: дуже особисте\n", encoding="utf-8")

    def fake_conf(key, default=None):
        if key == "astro.natal_file":
            return str(portrait)
        return default if not key.startswith("astro.subjects.") else None

    monkeypatch.setattr(mood.astro, "conf", fake_conf)
    monkeypatch.setattr(mood, "conf", fake_conf)
    monkeypatch.setattr(mood.astro, "natal_chart", lambda: None)
    monkeypatch.setattr(mood.astro, "natal_lines", lambda c: "ОБЧИСЛЕНА КАРТА")

    monkeypatch.setattr(mood.astro, "SUBJECT", "ghost")
    assert mood.natal_text() == "ОБЧИСЛЕНА КАРТА"

    monkeypatch.setattr(mood.astro, "SUBJECT", None)
    assert "дуже особисте" in mood.natal_text()
