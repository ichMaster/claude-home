"""t1072 — admin panel, phase 4. The dedup is the piece most likely to be wrong, so most
of these tests are about it being recorded and shown truthfully.
"""
import importlib.util
import json
import runpy
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import bruno                                                            # noqa: E402
import render                                                           # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "news_seen", ROOT / "status" / "tools" / "news_seen.py")

# --- TC1, TC2: the drop record ------------------------------------------------------------

def test_overlap_drop_is_recorded_with_its_reason(tmp_path, monkeypatch):
    seen = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(seen)
    monkeypatch.setattr(seen, "STATE", tmp_path / "news.json")
    earlier = {"url": "https://other.example/x",
               "title": "Canada and EU announce new alliance open to others",
               "words": sorted(seen.words("Canada and EU announce new alliance open")),
               "ts": datetime.now().isoformat()}
    why = seen.seen_reason([earlier], "https://example.com/a",
                           "Canada and EU announce new alliance")
    assert why and why["reason"] == "overlap" and why["score"] >= 0.6
    seen.record_drop({"ts": "2026-10-31T10:00:00", "title": "Canada and EU", **why})
    rec = json.loads((tmp_path / "news-dropped.jsonl").read_text(encoding="utf-8"))
    assert rec["reason"] == "overlap" and rec["matched"].startswith("Canada")


def test_link_drop_is_recorded_as_link(tmp_path, monkeypatch):
    seen = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(seen)
    monkeypatch.setattr(seen, "STATE", tmp_path / "news.json")
    earlier = {"url": "https://example.com/a?utm=1", "title": "Інший заголовок",
               "words": ["інший", "заголовок"]}
    why = seen.seen_reason([earlier], "https://example.com/a", "Зовсім нове")
    assert why["reason"] == "link"


def test_nothing_recorded_when_nothing_dropped(tmp_path, monkeypatch):
    seen = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(seen)
    monkeypatch.setattr(seen, "STATE", tmp_path / "news.json")
    assert seen.seen_reason([], "https://example.com/new", "Нова новина") is None
    assert not (tmp_path / "news-dropped.jsonl").exists()


def test_record_is_best_effort(tmp_path, monkeypatch):
    """An unwritable state dir must not break the digest — the record is a nicety."""
    seen = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(seen)
    monkeypatch.setattr(seen, "STATE", Path("/proc/nonexistent/news.json"))
    seen.record_drop({"ts": "now", "title": "x"})          # must not raise


# --- TC3: reading the drops -----------------------------------------------------------------

def test_dropped_news_newest_first_and_torn_line_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(bruno, "STATE", tmp_path)
    (tmp_path / "news-dropped.jsonl").write_text(
        json.dumps({"ts": "1", "title": "перший"}) + "\n"
        + '{"ts": "2", "title": "обір\n'
        + json.dumps({"ts": "3", "title": "третій"}) + "\n", encoding="utf-8")
    got = bruno.dropped_news()
    assert [d["title"] for d in got] == ["третій", "перший"]


def test_dropped_news_absent_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bruno, "STATE", tmp_path)
    assert bruno.dropped_news() == []


# --- TC4: the archive -------------------------------------------------------------------------

def archive(tmp_path):
    f = tmp_path / "youtube-archive.jsonl"
    f.write_text(
        json.dumps({"channel": "A", "title": "Все про лідар у робототехніці",
                    "link": "u1", "published": "2026-10-30T00:00:00+00:00"}) + "\n"
        + json.dumps({"channel": "B", "title": "Quantum computing explained",
                      "link": "u2", "published": "2026-09-01T00:00:00+00:00"}) + "\n"
        + "{торвана\n", encoding="utf-8")
    return f


def test_archive_stats(tmp_path):
    got = bruno.archive_stats(archive(tmp_path))
    assert got["count"] == 2 and got["channels"] == 2
    assert got["first"] == "2026-09-01" and got["last"] == "2026-10-30"


def test_archive_search_is_a_lookup_not_a_ranking(tmp_path):
    f = archive(tmp_path)
    assert [r["link"] for r in bruno.archive_search("ЛІДАР", archive=f)] == ["u1"]
    assert [r["link"] for r in bruno.archive_search("quantum", archive=f)] == ["u2"]
    assert bruno.archive_search("", archive=f) == []
    assert bruno.archive_search("нічого такого", archive=f) == []


# --- TC5: the chat -------------------------------------------------------------------------------

def test_chat_reports_turns_cap_and_drops(tmp_path, monkeypatch):
    monkeypatch.setattr(bruno, "STATE", tmp_path)
    (tmp_path / "bots").mkdir()
    now = datetime.now().astimezone()
    (tmp_path / "bots" / "bruno.json").write_text(json.dumps({
        "history": [{"role": "user", "text": "привіт"}],
        "answers": [(now - timedelta(minutes=5)).isoformat(),
                    (now - timedelta(hours=3)).isoformat()],
        "last_scope": "youtube"}), encoding="utf-8")
    (tmp_path / "bots" / "dropped.jsonl").write_text(
        json.dumps({"bot": "bruno", "why": "без тексту",
                    "shape": {"keys": ["photo"]}}) + "\n"
        + json.dumps({"bot": "zirka", "why": "чужий чат"}) + "\n", encoding="utf-8")
    got = bruno.bruno_chat()
    assert got["answers_this_hour"] == 1, "an answer from three hours ago is not this hour"
    assert got["last_scope"] == "youtube"
    assert len(got["dropped"]) == 1 and got["dropped"][0]["shape"]["keys"] == ["photo"]


# --- TC6: topics -----------------------------------------------------------------------------------

def test_topics_read_and_a_broken_one_is_reported(tmp_path):
    (tmp_path / "наука.json").write_text(json.dumps(
        {"назва": "Наука", "опис": "про науку", "запит": "science",
         "джерела": ["nature.com"]}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "зламана.json").write_text("{не json", encoding="utf-8")
    got = {t["id"]: t for t in bruno.topics(tmp_path)}
    assert got["наука"]["name"] == "Наука" and got["наука"]["sources"] == ["nature.com"]
    assert got["зламана"]["broken"]


# --- TC7: escaping ------------------------------------------------------------------------------------

def test_bruno_page_escapes_everything():
    html = render.render_bruno(
        news=[{"title": "<img src=x onerror=bad()>", "url": "http://e/", "ts": "2026-10-31"}],
        videos=("2026-10-31", [{"channel": "<b>ch</b>", "title": "<i>t</i>", "link": "u"}]),
        dropped=[{"ts": "2026-10-31T10:00:00", "title": "<u>drop</u>", "reason": "overlap",
                  "matched": "<em>earlier</em>", "score": 0.7}],
        stats={"count": 1, "first": "", "last": "", "channels": 1}, found=[], query="",
        chat={"history": [{"role": "user", "text": "<script>bad()</script>"}],
              "answers_this_hour": 0, "cap": 20, "last_scope": "", "dropped": []},
        topics=[{"id": "x", "broken": "", "name": "<b>n</b>", "about": "a",
                 "query": "<q>", "sources": [], "limit": ""}],
        prompts=[{"name": "p.md", "text": "<hr>"}])
    for raw in ("<img src=x", "<b>ch", "<i>t</i>", "<u>drop", "<em>earlier",
                "<script>bad()", "<b>n</b>", "<hr>"):
        assert raw not in html
    assert "&lt;img src=x" in html
