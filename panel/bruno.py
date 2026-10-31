"""The content channel, read from its own state — collectors for screen 5.

Bruno decides twice and used to show neither decision: which four items out of eight
topics go into a digest, and which candidates are dropped as repeats. The second is the
one worth seeing — a story silently absent looks exactly like a story that never existed.

The archive box is a human looking a word up in titles he already subscribes to. That is
not the system judging relevance, which is the owner's standing rule and the reason the
search in `status/bots/search.py` scores nothing: relevance is the model's job. Typing a
word into a box and getting the lines that contain it is a different act, and the only one
offered here.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path                                         # noqa: E402

HOME = Path(__file__).resolve().parents[1]
STATE = HOME / "status" / "state"
TOPICS = HOME / "status" / "topics"


def _lines(f: Path) -> list[dict]:
    """A JSONL file as records, skipping anything torn — these are append-only logs that
    may be written while this reads them."""
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        # a torn tail can parse as a scalar — `123` is valid JSON; only objects are records
        if isinstance(rec, dict):
            out.append(rec)
    return out


def sent_news(limit: int = 30) -> list[dict]:
    f = Path(str(path("digest.news_state", "status/state/news.json")))
    if not f.is_file():
        return []
    try:
        rows = json.loads(f.read_text(encoding="utf-8", errors="replace")).get("sent", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    return list(reversed(rows))[:limit]


def sent_videos(limit: int = 30) -> tuple[str, list[dict]]:
    f = STATE / "youtube-last-digest.json"
    if not f.is_file():
        return "", []
    try:
        d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return "", []
    return d.get("drained_at", ""), (d.get("items") or [])[:limit]


def dropped_news(limit: int = 40) -> list[dict]:
    """Candidates the dedup threw away, newest first — the section this screen is for."""
    return list(reversed(_lines(STATE / "news-dropped.jsonl")))[:limit]


def archive_stats(archive: Path | None = None) -> dict:
    f = archive or (STATE / "youtube-archive.jsonl")
    rows = _lines(f)
    days = sorted(r.get("published", "")[:10] for r in rows if r.get("published"))
    return {"count": len(rows),
            "first": days[0] if days else "",
            "last": days[-1] if days else "",
            "channels": len({r.get("channel") for r in rows if r.get("channel")})}


def archive_search(query: str, limit: int = 40, archive: Path | None = None) -> list[dict]:
    """Lines whose title contains the word, newest first. A lookup, not a ranking."""
    needle = (query or "").strip().lower()
    if not needle:
        return []
    rows = [r for r in _lines(archive or (STATE / "youtube-archive.jsonl"))
            if needle in str(r.get("title", "")).lower()]
    rows.sort(key=lambda r: r.get("published", ""), reverse=True)
    return rows[:limit]


def bruno_chat() -> dict:
    """The last turns, the hourly cap, and what was dropped with the shape it had."""
    f = STATE / "bots" / "bruno.json"
    st = {}
    if f.is_file():
        try:
            st = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            st = {}
    hour_ago = (datetime.now().astimezone() - timedelta(hours=1)).isoformat()
    answers = [t for t in st.get("answers", []) if t >= hour_ago]
    dropped = [d for d in reversed(_lines(STATE / "bots" / "dropped.jsonl"))
               if d.get("bot") == "bruno"][:20]
    return {
        "history": (st.get("history") or [])[-12:],
        "answers_this_hour": len(answers),
        "cap": int(conf("telegram.inbox.max_per_hour", 20)),
        "last_scope": st.get("last_scope", ""),
        "dropped": dropped,
    }


def topics(folder: Path | None = None) -> list[dict]:
    """The topic files. One that will not parse is reported, not fatal — eight files and
    a broken ninth should cost one row, not the screen."""
    d = folder or TOPICS
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            t = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            out.append({"id": f.stem, "broken": f"не читається: {exc}"})
            continue
        if not isinstance(t, dict):
            # `null` or a bare list is valid JSON and json.loads will not complain;
            # a topic that is not an object costs its row, not the screen
            out.append({"id": f.stem, "broken": "не обʼєкт, а "
                        f"{type(t).__name__} — тему не прочитати"})
            continue
        sources = t.get("джерела")
        out.append({"id": f.stem, "broken": "",
                    "name": t.get("назва", ""), "about": t.get("опис", ""),
                    "query": t.get("запит", ""),
                    "sources": [str(s) for s in sources]
                    if isinstance(sources, list) else [str(sources or "")],
                    "limit": t.get("межа") or t.get("ліміт") or ""})
    return out


def prompts() -> list[dict]:
    """Read-only in this phase; editing with a diff and a restart banner is phase 5."""
    out = []
    for rel in ("status/bots/bruno.md", "status/bots/intent.md",
                "status/bots/common.md", "status/youtube-prompt.md"):
        f = HOME / rel
        out.append({"name": rel,
                    "text": f.read_text(encoding="utf-8", errors="replace")
                    if f.is_file() else "(немає файлу)"})
    return out
