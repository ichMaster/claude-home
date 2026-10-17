#!/usr/bin/env python
"""Збирає кандидатів на дайджест і друкує їх для читання — без виклику моделі.

  candidates.py [тема ...]     — усі теми, якщо не вказано

Я читаю цей вивід сам і сам обираю, що варте уваги: ключ до API не потрібен,
бо відбір робить сесія, а не окремий виклик.
"""
import json, random, subprocess, sys
from pathlib import Path

HOME = Path.home() / "claude-home"
PYB = str(HOME / ".venv-voice" / "bin" / "python")
TOPICS = HOME / "status" / "topics"

argv = sys.argv[1:]
body_len = 1800 if "--повні" in argv else 600

# --навмання [N] — N випадкових тем зі списку (за замовчуванням 3),
# щоб дайджест не був щоразу тією самою вісімкою
rand_n = 0
if "--навмання" in argv:
    i = argv.index("--навмання")
    if len(argv) > i + 1 and argv[i + 1].isdigit():
        rand_n = int(argv[i + 1])
        argv.pop(i + 1)
    else:
        rand_n = 3
    argv.pop(i)

ids = [a for a in argv if not a.startswith("--")] or \
      sorted(p.stem for p in TOPICS.glob("*.json"))
if rand_n:
    ids = random.sample(ids, min(rand_n, len(ids)))
    print(f"# випадкові теми: {', '.join(ids)}")

for tid in ids:
    t = json.loads((TOPICS / f"{tid}.json").read_text(encoding="utf-8"))
    print(f"\n{'='*70}\n## {t['назва']}  [{tid}]\n{t.get('опис','')}")
    g = t.get("guardian")
    if g:
        raw = subprocess.run([PYB, str(HOME / "status/sources/guardian.py"),
                              g["запит"], g.get("розділ", "-"), "8"],
                             capture_output=True, text=True).stdout
        for a in (json.loads(raw) if raw.strip() else []):
            print(f"\n[G] {a['title']}  ({a['published'][:10]}, {a['section']})\n"
                  f"    {a['url']}\n    {a['lead'][:200]}\n    {a['body'][:body_len]}")
    raw = subprocess.run([PYB, str(HOME / "status/probes/news.py"), tid],
                         capture_output=True, text=True).stdout
    if raw.strip():
        for i in (json.loads(raw).get("value") or {}).get("items", []):
            print(f"\n[N] {i['title']}  ({i['source']})\n    {i['link']}")
