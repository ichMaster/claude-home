"""t1080 — admin panel, phase 7: Memory and Sources.

The facts screen exists for one answer nothing else gives — which facts did not fit the
prompt — and the sources screen writes to config.local.json, the file with no copy
anywhere, so the write tests matter more than the rendering ones.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import memory_screen                                                    # noqa: E402
import render                                                           # noqa: E402
import sources_screen                                                   # noqa: E402


# --- facts: what fits and what was cut --------------------------------------------------

def fake_facts(monkeypatch, rows, limit=3):
    import types
    monkeypatch.setattr(memory_screen, "_facts_module",
                        lambda: types.SimpleNamespace(load=lambda: rows))
    real = memory_screen.conf

    def fake(key, default=None):
        return {"memory.max_facts_in_prompt": limit, "memory.max_facts": 100,
                "memory.max_fact_chars": 240}.get(key, real(key, default))
    monkeypatch.setattr(memory_screen, "conf", fake)


def fact(i, pin=1, added="2026-10-01"):
    return {"file": None, "id": f"f{i}", "pin": pin, "tags": "", "added": added,
            "text": f"факт номер {i}"}


def test_cut_facts_are_the_screen_s_reason_to_exist(monkeypatch):
    """Five pinned facts and room for three: the other two are stored and silent, and
    nothing else in the system will tell you which."""
    fake_facts(monkeypatch, [fact(i) for i in range(1, 6)], limit=3)
    got = memory_screen.facts()
    assert len(got["in_prompt"]) == 3 and len(got["cut"]) == 2
    assert all(f["fits"] for f in got["in_prompt"])
    assert not any(f["fits"] for f in got["cut"])


def test_the_order_matches_what_the_prompt_builds(monkeypatch):
    """A different order here would show a different answer than the session wakes with."""
    rows = [fact(1, pin=2, added="2026-01-01"), fact(2, pin=1, added="2026-05-05"),
            fact(3, pin=1, added="2026-01-01")]
    fake_facts(monkeypatch, rows, limit=3)
    assert [f["id"] for f in memory_screen.facts()["in_prompt"]] == ["f3", "f2", "f1"]


def test_unpinned_are_separate_from_cut(monkeypatch):
    fake_facts(monkeypatch, [fact(1), fact(2, pin=0)], limit=5)
    got = memory_screen.facts()
    assert [f["id"] for f in got["in_prompt"]] == ["f1"]
    assert [f["id"] for f in got["unpinned"]] == ["f2"]
    assert got["cut"] == []


def test_counters_against_both_limits(monkeypatch):
    fake_facts(monkeypatch, [fact(i) for i in range(1, 6)], limit=3)
    got = memory_screen.facts()
    assert got["stored"] == 5 and got["max_in_prompt"] == 3 and got["max_stored"] == 100


# --- the archive ---------------------------------------------------------------------------

def test_archive_reports_absence_rather_than_failing(monkeypatch, tmp_path):
    monkeypatch.setattr(memory_screen, "path", lambda *a, **k: tmp_path / "nope.db")
    got = memory_screen.archive()
    assert got["exists"] is False and got["chunks"] == 0 and got["error"] == ""


def test_archive_counts_from_a_real_sqlite(monkeypatch, tmp_path):
    import sqlite3
    db = tmp_path / "m.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE files (path TEXT PRIMARY KEY, bytes INTEGER);
        CREATE TABLE chunks (id INTEGER PRIMARY KEY, project TEXT, session TEXT,
                             ts TEXT, role TEXT, text TEXT, emb BLOB);
        INSERT INTO files VALUES ('a', 1);
        INSERT INTO chunks VALUES (1, 'p', 's', '2026-10-31T10:00:00', 'user', 'текст', x'');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(memory_screen, "path", lambda *a, **k: db)
    got = memory_screen.archive()
    assert got["chunks"] == 1 and got["files"] == 1 and got["last"].startswith("2026-10-31")


# --- channels -------------------------------------------------------------------------------

def test_channels_carry_last_activity(monkeypatch, tmp_path):
    archive = tmp_path / "a.jsonl"
    archive.write_text(
        json.dumps({"channel": "Жвавий", "published": "2026-10-30T00:00:00"}) + "\n"
        + json.dumps({"channel": "Жвавий", "published": "2026-09-01T00:00:00"}) + "\n"
        + "{торвана\n", encoding="utf-8")
    monkeypatch.setattr(sources_screen, "conf", lambda key, default=None: {
        "probes.youtube.channels": [{"name": "Жвавий", "id": "UC1"},
                                    {"name": "Тихий", "id": "UC2"}],
        "probes.youtube.priority": ["Тихий"]}.get(key, default))
    rows = sources_screen.channels(archive)
    by = {c["name"]: c for c in rows}
    assert by["Жвавий"]["last"] == "2026-10-30", "the newest video, not the first line"
    assert by["Тихий"]["last"] == "" and by["Тихий"]["priority"] is True


def test_quiet_channels_sort_last():
    rows = [{"name": "Тихий", "last": ""}, {"name": "Жвавий", "last": "2026-10-30"}]
    assert [c["name"] for c in sources_screen.sort_channels(rows)] == ["Жвавий", "Тихий"]
    assert [c["name"] for c in sources_screen.sort_channels(rows, "name")] == \
        ["Жвавий", "Тихий"]


# --- the filter test box ---------------------------------------------------------------------

RULES = {"шум": ["udemymail.com"], "важливе": ["payments@"]}


def test_classify_matches_the_probe_s_own_order():
    assert "важливе" in sources_screen.classify("payments@bank", "рахунок", RULES)
    assert "шум" in sources_screen.classify("no@udemymail.com", "курс", RULES)
    assert sources_screen.classify("хтось@там", "привіт", RULES) == "звичайне"


def test_important_outranks_noise():
    """The probe raises severity on важливе, so a message matching both must not be hidden."""
    rules = {"шум": ["bank"], "важливе": ["payments@"]}
    assert "важливе" in sources_screen.classify("payments@bank", "рахунок", rules)


# --- writing to the personal config ------------------------------------------------------------

def local_config(monkeypatch, tmp_path):
    f = tmp_path / "config.local.json"
    f.write_text(json.dumps({
        "astro": {"birth": {"date": "1900-01-01"}},
        "probes": {"youtube": {"channels": [{"name": "Один", "id": "UC1"},
                                            {"name": "Два", "id": "UC2"}],
                               "priority": []}}}, ensure_ascii=False), encoding="utf-8")
    f.chmod(0o600)
    monkeypatch.setattr(sources_screen, "LOCAL", f)
    monkeypatch.setattr(sources_screen, "conf", lambda key, default=None: default)
    return f


def test_disabling_a_channel_keeps_everything_else(monkeypatch, tmp_path):
    f = local_config(monkeypatch, tmp_path)
    said = sources_screen.set_channel("Один", off=True)
    data = json.loads(f.read_text(encoding="utf-8"))
    assert data["astro"]["birth"]["date"] == "1900-01-01", "unrelated keys survive"
    chans = data["probes"]["youtube"]["channels"]
    assert chans[0]["off"] is True and "off" not in chans[1]
    assert "вимкнено" in said


def test_priority_toggles_both_ways(monkeypatch, tmp_path):
    f = local_config(monkeypatch, tmp_path)
    sources_screen.set_channel("Два", priority=True)
    assert json.loads(f.read_text(encoding="utf-8"))["probes"]["youtube"]["priority"] == ["Два"]
    sources_screen.set_channel("Два", priority=False)
    assert json.loads(f.read_text(encoding="utf-8"))["probes"]["youtube"]["priority"] == []


def test_unknown_channel_changes_nothing(monkeypatch, tmp_path):
    f = local_config(monkeypatch, tmp_path)
    before = f.read_text(encoding="utf-8")
    said = sources_screen.set_channel("Неіснуючий", off=True)
    assert f.read_text(encoding="utf-8") == before
    assert "немає" in said


def test_the_write_keeps_mode_600(monkeypatch, tmp_path):
    """The file holds birth data and the calendar id; a widened mode would be a leak."""
    f = local_config(monkeypatch, tmp_path)
    sources_screen.set_channel("Один", off=True)
    assert f.stat().st_mode & 0o777 == 0o600


# --- rendering ------------------------------------------------------------------------------------

def test_memory_page_escapes_and_marks_the_cut():
    html = render.render_memory(
        facts={"in_prompt": [{"id": "a", "pin": 1, "added": "", "tags": "",
                              "text": "<b>усередині</b>", "chars": 9, "fits": True}],
               "cut": [{"id": "b", "pin": 1, "added": "", "tags": "",
                        "text": "<i>відрізано</i>", "chars": 9, "fits": False}],
               "unpinned": [], "stored": 2, "max_stored": 100, "max_in_prompt": 1,
               "max_chars": 240},
        archive={"exists": True, "size": 1024, "chunks": 5, "files": 1,
                 "last": "2026-10-31 10:00", "error": "", "file": "m.db"},
        found=[], query="", token="SECRET", message="")
    assert "<b>усередині" not in html and "<i>відрізано" not in html
    assert "не влізли" in html
    assert 'name="token" value="SECRET"' in html


def test_sources_page_escapes_channel_names():
    html = render.render_sources(
        channels=[{"name": "<img src=x>", "id": "UC1", "handle": "", "off": False,
                   "priority": False, "last": "2026-10-30"}],
        filters={"mail": {"шум": ["<b>n</b>"], "важливе": []},
                 "linkedin_personal": [], "linkedin_noise": [], "facebook": []},
        topics=[], probe="", token="SECRET", message="", query="", order="activity")
    assert "<img src=x>" not in html and "<b>n</b>" not in html
    assert "&lt;img src=x&gt;" in html
