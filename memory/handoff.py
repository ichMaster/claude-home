#!/usr/bin/env python
"""Build a handoff note from the tail of the current session's transcript.

  memory/handoff.py [--chars N] [--turns N]

Writes `memory/handoff.md`, which `start.sh` injects into the system prompt of the next
session. The point is not to carry the conversation over — that is what `--continue`
does — but to carry the **thread**: what we are doing, what was just decided, what is
open. A good handoff is one page; the previous conversation stays searchable in the
archive either way.

The note is produced by a headless session reading the last turns of the transcript, so
it works even when the main session is wedged.
"""
import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

HOME = path("paths.home")
OUT = HOME / "memory" / "handoff.md"
TURNS = int(sys.argv[sys.argv.index("--turns") + 1]) if "--turns" in sys.argv else conf("memory.handoff_turns", 60)
MAX_CHARS = int(sys.argv[sys.argv.index("--chars") + 1]) if "--chars" in sys.argv else conf("memory.handoff_max_chars", 6000)

project = path("paths.transcripts") / "-home-ich-claude-home"
files = sorted(project.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
if not files:
    sys.exit("транскриптів немає")
latest = files[-1]

# the tail of the conversation: user asks and assistant answers, tool noise dropped
turns = []
with latest.open(encoding="utf-8") as fh:
    for line in fh:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        msg = rec.get("message") or {}
        role = msg.get("role") or rec.get("type")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
        text = text.strip()
        if not text or text.startswith("[результат]"):
            continue
        turns.append(f"{role}: {text[:1200]}")

tail = "\n\n".join(turns[-TURNS:])[-60000:]

PROMPT = f"""Ти читаєш хвіст розмови між користувачем і його асистентом Ноосом.
Склади естафетну записку для наступної сесії Нооса — вона почнеться з чистого контексту
і побачить лише цю записку плюс закріплені факти.

Формат, українською, не більше {MAX_CHARS} символів:

## Над чим працюємо
2-4 рядки: поточна задача і стан.

## Щойно зроблено
5-8 пунктів: конкретні зміни, файли, рішення. Без переказу обговорень.

## Відкриті питання
Те, на що користувач ще не відповів або що лишилось недоробленим.

## Чого не робити
Відхилені варіанти й граблі, на які вже наступали, щоб не повторювати.

Пиши фактами. Не вигадуй того, чого немає в тексті. Нічого, крім самої записки.

--- хвіст розмови ---
{tail}
"""

res = subprocess.run(
    ["claude", "-p", PROMPT, "--settings", str(HOME / "status" / "digest-settings.json")],
    capture_output=True, text=True, timeout=300)
note = (res.stdout or "").strip()
if not note:
    sys.exit(f"не вдалося скласти записку: {(res.stderr or '')[:200]}")

OUT.write_text(
    f"<!-- handoff written {datetime.now().isoformat(timespec='seconds')} "
    f"from {latest.stem} -->\n\n{note[:MAX_CHARS]}\n", encoding="utf-8")
print(f"{OUT} — {len(note)} символів із {len(turns)} реплік")
