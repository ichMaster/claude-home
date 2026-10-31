"""t1033 — the reference is cut into days by the model, never by a header regex, and a
reference about today makes the day recompute.
"""
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("noos_astro_learn",
                                               ROOT / "status" / "astro_learn.py")
learn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(learn)

WEEK = "➲ Пт 30 октября\nЛуна в Тельце\n\nВс 1 ноября\nЛуна в Близнецах"


def answer(blocks):
    """What the splitting call returns: one line of JSON and nothing else."""
    return json.dumps(blocks, ensure_ascii=False)


def test_split_uses_the_model(monkeypatch):
    """TC1: the days come from the call's answer — no month table is consulted."""
    seen = {}

    def fake_call(prompt, model="", timeout=0):
        seen["prompt"] = prompt
        return answer([{"day": "2026-10-30", "text": "Луна в Тельце"},
                       {"day": "2026-11-01", "text": "Луна в Близнецах"}])

    monkeypatch.setattr(learn, "ask", fake_call)
    got = learn.split_days(WEEK, date(2026, 10, 31))
    assert [d.isoformat() for d, _ in got] == ["2026-10-30", "2026-11-01"]
    assert got[1][1] == "Луна в Близнецах"
    assert "Луна в Тельце" in seen["prompt"], "the text has to reach the call"


def test_split_falls_back_to_one_block(monkeypatch):
    """TC2: a failed or unusable call keeps the whole text under the given date."""
    def boom(prompt, model="", timeout=0):
        raise RuntimeError("виклик не вдався")

    monkeypatch.setattr(learn, "ask", boom)
    got = learn.split_days(WEEK, date(2026, 10, 31))
    assert len(got) == 1
    assert got[0][0] == date(2026, 10, 31)
    assert got[0][1] == WEEK

    monkeypatch.setattr(learn, "ask", lambda *a, **k: "не знаю")
    got = learn.split_days(WEEK, date(2026, 10, 31))
    assert got == [(date(2026, 10, 31), WEEK)]


def test_split_drops_a_malformed_block(monkeypatch):
    """TC3: trust the answer only where it is well-formed."""
    monkeypatch.setattr(learn, "ask", lambda *a, **k: answer([
        {"day": "позавчора", "text": "сміття"},
        {"day": "2026-11-01", "text": "Луна в Близнецах"},
        {"day": "2026-11-02", "text": "   "},
    ]))
    got = learn.split_days(WEEK, date(2026, 10, 31))
    assert [d.isoformat() for d, _ in got] == ["2026-11-01"]
