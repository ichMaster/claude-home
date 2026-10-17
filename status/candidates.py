#!/usr/bin/env python
"""Collect digest candidates and print them for reading — no model call.

  candidates.py [topic ...]    — all topics when none is given

The session reads this output and picks what matters itself, so no API key is
needed: the selection is made by the session, not by a separate call.
"""
import json, random, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

HOME = path("paths.home")
PYB = str(HOME / ".venv-voice" / "bin" / "python")
TOPICS = HOME / "status" / "topics"

argv = sys.argv[1:]
body_len = 1800 if "--full" in argv else 600

# --random [N] picks N random topics (3 by default) so the digest is not
# always the same eight
rand_n = 0
if "--random" in argv:
    i = argv.index("--random")
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
