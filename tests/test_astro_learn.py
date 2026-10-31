"""t1033 — the reference is cut into days by the model, never by a header regex, and a
reference about today makes the day recompute.

t1070 — a reference ingested with `add --file` leaves the inbox, so the panel's
«чекають на внесення» stays honest and «внести» cannot duplicate the store.
"""
import importlib.util
import json
import sys
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


# --- t1070: an ingested reference leaves the inbox --------------------------------------

def test_consume_moves_an_inbox_file(monkeypatch, tmp_path):
    """TC1 (regression): after a successful ingest the file is in `ingested/`, raw text
    intact, and the inbox's own listing no longer shows it."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    f = inbox / "20261031-120000-2026-10-31.txt"
    f.write_text("еталон", encoding="utf-8")
    monkeypatch.setattr(learn, "INBOX", inbox)
    moved = learn.consume(f)
    assert moved == inbox / "ingested" / f.name
    assert moved.read_text(encoding="utf-8") == "еталон"
    assert not f.exists()
    assert list(inbox.glob("*.txt")) == []


def test_consume_leaves_foreign_files_alone(monkeypatch, tmp_path):
    """TC2: `add --file` on an arbitrary path must not relocate the owner's files."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    monkeypatch.setattr(learn, "INBOX", inbox)
    f = tmp_path / "чужий.txt"
    f.write_text("не з inbox", encoding="utf-8")
    assert learn.consume(f) is None
    assert f.exists()


def test_consume_does_not_overwrite_on_collision(monkeypatch, tmp_path):
    """TC3: a name already in `ingested/` keeps its content; the newcomer gets a suffix."""
    inbox = tmp_path / "inbox"
    (inbox / "ingested").mkdir(parents=True)
    monkeypatch.setattr(learn, "INBOX", inbox)
    (inbox / "ingested" / "a.txt").write_text("старий", encoding="utf-8")
    f = inbox / "a.txt"
    f.write_text("новий", encoding="utf-8")
    moved = learn.consume(f)
    assert moved is not None and moved.name != "a.txt"
    assert (inbox / "ingested" / "a.txt").read_text(encoding="utf-8") == "старий"
    assert moved.read_text(encoding="utf-8") == "новий"


def test_add_file_consumes_the_parked_reference(monkeypatch, tmp_path):
    """TC4: the wiring — `add --file <inbox file>` records the reference and consumes
    the file."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    store = tmp_path / "ref.jsonl"
    monkeypatch.setattr(learn, "INBOX", inbox)
    monkeypatch.setattr(learn, "store", lambda: store)
    f = inbox / "20261031-120000-2026-10-31.txt"
    f.write_text("текст еталона", encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["astro_learn.py", "add", "--file", str(f), "--day", "2026-10-31"])
    assert learn.main() == 0
    rec = json.loads(store.read_text(encoding="utf-8").splitlines()[0])
    assert rec["text"] == "текст еталона"
    assert not f.exists(), "the ingested file must leave the inbox"
    assert (inbox / "ingested" / f.name).is_file()
