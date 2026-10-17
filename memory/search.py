#!/usr/bin/env python
"""Пошук по всіх минулих сесіях: гібрид повнотекстового і смислового.

  memory/search.py "запит" [скільки]

Два списки (BM25 і косинус по ембедінгах) зливаються ранговим злиттям,
тому знаходиться і дослівний збіг, і переказ іншими словами.
"""
import sys, sqlite3, numpy as np
from pathlib import Path

DB = Path.home() / "claude-home" / "memory" / "sessions.db"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
K = 60  # константа рангового злиття

q = sys.argv[1]
top = int(sys.argv[2]) if len(sys.argv) > 2 else 8
db = sqlite3.connect(DB)

# 1. повнотекстовий: беремо слова довші за 2 символи, зшиваємо через OR
words = [w for w in "".join(c if c.isalnum() else " " for c in q).split() if len(w) > 2]
bm = []
if words:
    try:
        bm = [r[0] for r in db.execute(
            "SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 50",
            (" OR ".join(words),))]
    except sqlite3.OperationalError:
        bm = []

# 2. смисловий: косинус по ембедінгах
from fastembed import TextEmbedding
qv = np.asarray(list(TextEmbedding(model_name=MODEL, cache_dir=str(Path.home() / "claude-home" / "memory" / "models")).embed([q]))[0], dtype="float32")
ids, mat = [], []
for i, blob in db.execute("SELECT id, emb FROM chunks"):
    ids.append(i); mat.append(np.frombuffer(blob, dtype="float32"))
sem = []
if mat:
    M = np.vstack(mat)
    sims = M @ qv / (np.linalg.norm(M, axis=1) * np.linalg.norm(qv) + 1e-9)
    sem = [ids[j] for j in np.argsort(-sims)[:50]]

# 3. рангове злиття
score = {}
for rank, i in enumerate(bm):
    score[i] = score.get(i, 0) + 1 / (K + rank)
for rank, i in enumerate(sem):
    score[i] = score.get(i, 0) + 1 / (K + rank)

best = sorted(score.items(), key=lambda kv: -kv[1])[:top]
if not best:
    print("нічого не знайдено")
for i, s in best:
    proj, sess, ts, role, text = db.execute(
        "SELECT project,session,ts,role,text FROM chunks WHERE id=?", (i,)).fetchone()
    if proj == "факти":
        print(f"\n━━ закріплений факт · {sess} · вага {s:.3f}")
    else:
        print(f"\n━━ {ts[:19] or '?'} · {role} · {proj} · сесія {sess[:8]} · вага {s:.3f}")
    print(text[:700].strip())
