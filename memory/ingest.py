#!/usr/bin/env python
"""Index session transcripts into SQLite: full-text search plus embeddings.

  memory/ingest.py            — index what is new
  memory/ingest.py --rebuild  — rebuild from scratch

Incremental: remembers how many bytes of each file have already been read.
"""
import json, os, sqlite3, sys, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

ROOT = path("paths.transcripts")
DB = path("memory.db")
MODEL = conf("memory.model")
CHUNK, OVERLAP = 1400, 200

def text_of(rec):
    """Extract readable text from one transcript record."""
    m = rec.get("message")
    if not isinstance(m, dict):
        return None
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = []
        for part in c:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                out.append(part["text"])
            elif part.get("type") == "tool_use":
                name = part.get("name", "?")
                inp = json.dumps(part.get("input", {}), ensure_ascii=False)[:400]
                out.append(f"[виклик {name}] {inp}")
            elif part.get("type") == "tool_result":
                r = part.get("content")
                if isinstance(r, list):
                    r = " ".join(x.get("text", "") for x in r if isinstance(x, dict))
                if isinstance(r, str) and r.strip():
                    out.append(f"[результат] {r[:400]}")
        return "\n".join(x for x in out if x)
    return None

def chunks(s):
    s = s.strip()
    if len(s) <= CHUNK:
        return [s] if s else []
    out, i = [], 0
    while i < len(s):
        out.append(s[i:i + CHUNK])
        i += CHUNK - OVERLAP
    return out

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, bytes INTEGER);
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY, project TEXT, session TEXT, ts TEXT,
        role TEXT, text TEXT, emb BLOB);
    CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
        text, content='chunks', content_rowid='id', tokenize='unicode61');
    """)
    return db

def main():
    rebuild = "--rebuild" in sys.argv
    db = connect()
    if rebuild:
        db.executescript("DELETE FROM files; DELETE FROM chunks; DELETE FROM fts;")
    pending = []
    for f in sorted(ROOT.rglob("*.jsonl")):
        size = f.stat().st_size
        row = db.execute("SELECT bytes FROM files WHERE path=?", (str(f),)).fetchone()
        done = row[0] if row else 0
        if done >= size:
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            fh.seek(done)
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") not in ("user", "assistant"):
                    continue
                t = text_of(rec)
                if not t or len(t.strip()) < 40:
                    continue
                for ch in chunks(t):
                    pending.append((f.parent.name, f.stem, rec.get("timestamp") or "",
                                    rec.get("type"), ch))
        db.execute("INSERT INTO files(path,bytes) VALUES(?,?) "
                   "ON CONFLICT(path) DO UPDATE SET bytes=excluded.bytes", (str(f), size))
    # facts are always reindexed from scratch: few of them, edited often
    facts_dir = Path.home() / "claude-home" / "memory" / "facts"
    if facts_dir.exists():
        db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE project='факти')")
        db.execute("DELETE FROM chunks WHERE project='факти'")
        for ff in sorted(facts_dir.glob("*.md")):
            body = ff.read_text(encoding="utf-8").split("\n---\n", 1)[-1].strip()
            if body:
                pending.append(("факти", ff.stem, "", "fact", body))

    # imported extracts from other agents: same, small and rarely changed
    imp_dir = Path.home() / "claude-home" / "memory" / "import"
    for src in sorted(imp_dir.glob("*/")) if imp_dir.exists() else []:
        proj = src.name
        db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE project=?)", (proj,))
        db.execute("DELETE FROM chunks WHERE project=?", (proj,))
        for mf in sorted(src.glob("*.md")):
            if mf.name == "README.md":
                continue
            for ch in chunks(mf.read_text(encoding="utf-8")):
                pending.append((proj, mf.stem, "", "import", ch))

    if not pending:
        print("нового немає")
        db.commit()
        return
    print(f"нових фрагментів: {len(pending)}, рахую ембедінги…", flush=True)
    from fastembed import TextEmbedding
    CACHE = str(Path.home() / "claude-home" / "memory" / "models")
    import numpy as np
    model = TextEmbedding(model_name=MODEL, cache_dir=CACHE)
    vecs = list(model.embed([p[4] for p in pending]))
    for (proj, sess, ts, role, text), v in zip(pending, vecs):
        cur = db.execute(
            "INSERT INTO chunks(project,session,ts,role,text,emb) VALUES(?,?,?,?,?,?)",
            (proj, sess, ts, role, text, np.asarray(v, dtype="float32").tobytes()))
        db.execute("INSERT INTO fts(rowid,text) VALUES(?,?)", (cur.lastrowid, text))
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"готово: у базі {n} фрагментів, {DB}")

main()
