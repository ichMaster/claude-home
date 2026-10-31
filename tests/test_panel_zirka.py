"""t1068 — admin panel, phase 3. The first phase that writes, so half of these tests are
about the write path refusing what it should refuse.
"""
import subprocess
import sys
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import render                                                           # noqa: E402
import server                                                           # noqa: E402
import zirka                                                            # noqa: E402

LOG = """\
===== 2026-10-30 =====

--- підсумок ---
ПІДСУМОК: учора.

===== 2026-10-31 =====

--- факти ---
t1 транзитний Плутон квадратура натальна Венера

--- зважування ---
ОСНОВНЕ: t1

--- підсумок ---
КОРОТКО: День про перегляд.
ПІДСУМОК: Тон тримає Плутон.
ІСТОРІЯ: Довга історія дня.
ГОЛОВНЕ: Плутон квадратура Венера.
НАСАМКІНЕЦЬ: Важливе: спокій.

===== 2026-10-31 =====

--- підсумок (перероблено) ---
КОРОТКО: Перероблений день.
ПІДСУМОК: Інший тон.
"""


# --- TC1: blocks against budgets --------------------------------------------------------

def test_blocks_measured_against_their_budgets():
    summary = "КОРОТКО: " + "я" * 400 + "\nПІДСУМОК: коротко"
    blocks = {b["name"]: b for b in zirka.reading_blocks(summary)}
    assert blocks["КОРОТКО"]["over"] is True and blocks["КОРОТКО"]["budget"] == 300
    assert blocks["ПІДСУМОК"]["over"] is False


def test_missing_block_is_named_not_omitted():
    blocks = zirka.reading_blocks("КОРОТКО: лише один блок")
    assert len(blocks) == 5
    assert blocks[0]["missing"] is False
    assert all(b["missing"] for b in blocks[1:])


# --- TC2: runs ----------------------------------------------------------------------------

def test_runs_newest_first_with_their_stages():
    runs = zirka.day_runs(LOG, "2026-10-31")
    assert len(runs) == 2, "a resumed run is its own block, not merged into the morning"
    assert runs[0]["stages"][0]["name"] == "підсумок (перероблено)"
    assert [s["name"] for s in runs[1]["stages"]] == ["факти", "зважування", "підсумок"]
    assert "Тон тримає Плутон" in runs[1]["summary"]


def test_day_with_no_block():
    assert zirka.day_runs(LOG, "2020-01-01") == []
    assert zirka.day_runs("", "2026-10-31") == []


# --- TC3: parked references ----------------------------------------------------------------

def test_parked_lists_newest_first(tmp_path):
    (tmp_path / "20261031-120000-2026-10-31.txt").write_text("перший", encoding="utf-8")
    (tmp_path / "20261031-130000-2026-11-01.txt").write_text("другий", encoding="utf-8")
    got = zirka.parked(tmp_path)
    assert [p["day"] for p in got] == ["2026-11-01", "2026-10-31"]
    assert got[0]["chars"] == 6


def test_parked_empty(tmp_path):
    assert zirka.parked(tmp_path) == []
    assert zirka.parked(tmp_path / "missing") == []


# --- TC4, TC5, TC6: the write path -----------------------------------------------------------

def calls(monkeypatch):
    seen = []

    def run(cmd, **kw):
        seen.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    return seen


def test_reference_is_stored_and_learned_on_request(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "HOME", tmp_path)
    seen = calls(monkeypatch)
    msg = server.save_reference("☽ календар", "2026-11-01", "автор", learn=True)
    written = list((tmp_path / "status" / "state" / "astro-reference-inbox").glob("*.txt"))
    assert written and written[0].read_text(encoding="utf-8") == "☽ календар"
    cmd = [c for c in seen if any("astro_learn.py" in str(p) for p in c)][0]
    assert "--file" in cmd and "--learn" in cmd
    assert cmd[cmd.index("--day") + 1] == "2026-11-01"
    assert "записано" in msg


def test_reference_without_learn_only_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "HOME", tmp_path)
    seen = calls(monkeypatch)
    server.save_reference("текст", "2026-11-01", "", learn=False)
    cmd = [c for c in seen if any("astro_learn.py" in str(p) for p in c)][0]
    assert "--learn" not in cmd


def test_empty_reference_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "HOME", tmp_path)
    seen = calls(monkeypatch)
    msg = server.save_reference("   ", "2026-11-01", "", learn=False)
    assert "порожн" in msg.lower()
    assert seen == [], "nothing may run for an empty submission"


def test_failure_is_reported_not_swallowed(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "HOME", tmp_path)

    def failing(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="щось пішло не так")
    monkeypatch.setattr(subprocess, "run", failing)
    msg = server.save_reference("текст", "2026-11-01", "", learn=True)
    assert "не так" in msg or "не вдал" in msg


def test_csrf_token_is_required():
    """No authentication guards this port, so a page on any LAN origin could post here —
    and these buttons start eight-minute pipelines."""
    assert server.check_token(server.FORM_TOKEN) is True
    assert server.check_token("") is False
    assert server.check_token("guessed") is False


# --- TC7: escaping -----------------------------------------------------------------------------

def test_zirka_page_escapes_free_text():
    blocks = zirka.reading_blocks("КОРОТКО: <img src=x onerror=bad()>")
    html = render.render_zirka(
        day="2026-10-31", blocks=blocks,
        runs=[{"day": "2026-10-31",
               "stages": [{"name": "факти", "text": "<script>bad()</script>"}],
               "summary": ""}],
        facts=["<b>факт</b>"], own_rules="<i>правило</i>", ref_rules="",
        feedback=[{"ts": "2026-10-31T10:00:00", "text": "<u>відгук</u>"}],
        refs=[], parked=[{"name": "a.txt", "day": "2026-10-31", "chars": 5,
                          "head": "<em>еталон</em>"}],
        token="t", message="")
    for raw in ("<img src=x", "<script>bad()", "<b>факт", "<i>правило", "<u>відгук",
                "<em>еталон"):
        assert raw not in html
    assert "&lt;img src=x" in html


def test_zirka_page_carries_the_token_in_every_form():
    html = render.render_zirka(day="2026-10-31", blocks=[], runs=[], facts=[],
                               own_rules="", ref_rules="", feedback=[], refs=[],
                               parked=[], token="SECRET", message="")
    assert html.count('name="token" value="SECRET"') >= 2
