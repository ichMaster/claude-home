"""t1039: video candidates come back by recency, never filtered by the query string.

Pure and offline — writes a temporary archive and points search.ARCHIVE at it.
"""
import json

import search


def _write_archive(tmp_path, rows):
    f = tmp_path / "archive.jsonl"
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                 encoding="utf-8")
    return f


def test_videos_not_filtered_by_query(tmp_path, monkeypatch):
    rows = [
        {"channel": "A", "title": "totally unrelated title", "link": "u1",
         "published": "2026-10-30T00:00:00+00:00"},
        {"channel": "B", "title": "older one", "link": "u2",
         "published": "2026-01-01T00:00:00+00:00"},
    ]
    monkeypatch.setattr(search, "ARCHIVE", _write_archive(tmp_path, rows))
    # a query that matches NO title must still return both rows — relevance is the LLM's job
    got = search.videos("quantum lidar robots")
    assert {r["link"] for r in got} == {"u1", "u2"}
    # recency order: newest first
    assert got[0]["link"] == "u1"


def test_videos_pool_cap(tmp_path, monkeypatch):
    rows = [{"channel": "C", "title": f"v{i}", "link": f"u{i}",
             "published": f"2026-10-{(i % 28) + 1:02d}T00:00:00+00:00"} for i in range(50)]
    monkeypatch.setattr(search, "ARCHIVE", _write_archive(tmp_path, rows))
    assert len(search.videos("x", limit=10)) == 10
