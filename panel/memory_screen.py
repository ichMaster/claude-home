"""Facts and the conversation archive — collectors for screen 6.

The one thing here that cannot be learned any other way: **which facts did not fit**. The
system prompt takes the top `memory.max_facts_in_prompt` pinned facts; the rest are stored
and silent. Today the only way to know what was cut is to count by hand.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path                                         # noqa: E402

HOME = Path(__file__).resolve().parents[1]


def _facts_module():
    """Load `memory/facts.py` by path, never by putting `memory/` on sys.path.

    That directory holds `search.py`, which would shadow `status/bots/search.py` — the
    module Bruno's search lives in — for every importer in the process. It is a
    whole-process effect from one screen's convenience, and it showed up as two unrelated
    tests failing only when the suite ran together.
    """
    f = HOME / "memory" / "facts.py"
    spec = importlib.util.spec_from_file_location("noos_facts", f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def facts() -> dict:
    """Every fact, split into the ones that reach the prompt and the ones that do not.

    The split repeats `facts.prompt()`'s own ordering — pinned first, by pin level then by
    the day added — because showing a different order here would be showing a different
    answer than the one the session actually wakes up with.
    """
    rows = _facts_module().load()
    limit = int(conf("memory.max_facts_in_prompt", 25))
    pinned = sorted([f for f in rows if f["pin"] > 0],
                    key=lambda f: (f["pin"], f["added"]))
    unpinned = [f for f in rows if f["pin"] <= 0]

    max_chars = int(conf("memory.max_fact_chars", 240))

    def shape(f, fits):
        text = " ".join(f["text"].split())
        # `facts.prompt()` cuts a fact at `memory.max_fact_chars`; printing it in full here
        # shows more than the session is told, which is the one thing this screen must not
        # do (t1114).
        return {"id": f["id"], "pin": f["pin"], "added": f["added"],
                "tags": f["tags"], "text": text, "chars": len(text), "fits": fits,
                "truncated": fits and len(text) > max_chars,
                "in_prompt_chars": min(len(text), max_chars) if fits else 0}

    out = [shape(f, True) for f in pinned[:limit]]
    cut = [shape(f, False) for f in pinned[limit:]]
    return {
        "in_prompt": out,
        "cut": cut,
        "unpinned": [shape(f, False) for f in unpinned],
        "stored": len(rows),
        "max_stored": int(conf("memory.max_facts", 100)),
        "max_in_prompt": limit,
        "max_chars": int(conf("memory.max_fact_chars", 240)),
    }


def archive() -> dict:
    """Size and freshness of the transcript index, without loading the model."""
    db = path("memory.db")
    out = {"file": str(db), "exists": bool(db and db.is_file()), "size": 0,
           "chunks": 0, "files": 0, "last": "", "error": ""}
    if not out["exists"]:
        return out
    out["size"] = db.stat().st_size
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            out["chunks"] = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            out["files"] = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            row = con.execute("SELECT MAX(ts) FROM chunks").fetchone()
            out["last"] = (row[0] or "")[:16].replace("T", " ")
        finally:
            con.close()
    except sqlite3.Error as exc:
        out["error"] = str(exc)
    return out


def search(query: str, limit: int = 15) -> list[dict]:
    """Full-text search over the archive.

    Deliberately FTS only, not the hybrid query `search.sh` runs: the embedding model is
    240 MB and loading it inside a web request would make the page take half a minute.
    The screen says so rather than quietly answering a narrower question.
    """
    db = path("memory.db")
    if not query.strip() or not db or not db.is_file():
        return []
    out = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT c.ts, c.project, c.role, c.text FROM fts "
                "JOIN chunks c ON c.id = fts.rowid WHERE fts MATCH ? "
                "ORDER BY rank LIMIT ?", (query, limit)).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return [{"ts": "", "project": "", "role": "", "text": f"пошук не вдався: {exc}"}]
    for ts, project, role, text in rows:
        out.append({"ts": (ts or "")[:16].replace("T", " "), "project": project or "",
                    "role": role or "", "text": " ".join((text or "").split())[:400]})
    return out
