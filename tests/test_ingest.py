"""t1049 — the transcript index must survive --rebuild (FTS5 external-content delete order)
and must not lose or duplicate records when a transcript grows mid-read."""
import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# loaded by file path: putting memory/ on sys.path would shadow status/bots/search.py
# (memory/ has its own search.py) for the other tests
_spec = importlib.util.spec_from_file_location("memory_ingest", ROOT / "memory" / "ingest.py")
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    CREATE TABLE files (path TEXT PRIMARY KEY, bytes INTEGER);
    CREATE TABLE chunks (
        id INTEGER PRIMARY KEY, project TEXT, session TEXT, ts TEXT,
        role TEXT, text TEXT, emb BLOB);
    CREATE VIRTUAL TABLE fts USING fts5(
        text, content='chunks', content_rowid='id', tokenize='unicode61');
    """)
    return db


def add_chunk(db, text):
    cur = db.execute("INSERT INTO chunks(project,session,ts,role,text,emb) "
                     "VALUES('p','s','','user',?,x'')", (text,))
    db.execute("INSERT INTO fts(rowid,text) VALUES(?,?)", (cur.lastrowid, text))
    return cur.lastrowid


def test_clear_all_leaves_fts_consistent():
    """TC1: after clear_all + re-insert, the old term is gone, the new one found, and the
    FTS5 integrity check passes (the old delete order left a malformed index)."""
    db = make_db()
    add_chunk(db, "старий запис про акваріум")
    ingest.clear_all(db)
    new_id = add_chunk(db, "новий запис про теплицю")
    assert db.execute("SELECT rowid FROM fts WHERE fts MATCH 'акваріум'").fetchall() == []
    assert db.execute("SELECT rowid FROM fts WHERE fts MATCH 'теплицю'").fetchall() == [(new_id,)]
    db.execute("INSERT INTO fts(fts) VALUES('integrity-check')")   # raises if malformed


def test_tail_lines_torn_then_completed(tmp_path):
    """TC2: the torn tail is not consumed; once completed it is read exactly once."""
    f = tmp_path / "t.jsonl"
    f.write_bytes(b'{"a": 1}\n{"b": ')
    lines, off = ingest.tail_lines(f, 0)
    assert lines == ['{"a": 1}\n']
    assert off == len(b'{"a": 1}\n')
    with f.open("ab") as fh:
        fh.write(b'2}\n')
    lines, off2 = ingest.tail_lines(f, off)
    assert lines == ['{"b": 2}\n']
    assert off2 == f.stat().st_size


def test_tail_lines_idempotent(tmp_path):
    """TC3: nothing new → nothing read, offset unchanged."""
    f = tmp_path / "t.jsonl"
    f.write_bytes(b'{"a": 1}\n')
    _, off = ingest.tail_lines(f, 0)
    lines, off2 = ingest.tail_lines(f, off)
    assert lines == [] and off2 == off
