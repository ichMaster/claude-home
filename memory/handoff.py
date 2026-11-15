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

The transcript is the newest *conversation*, not the newest file (t1164): every headless
`claude -p` run — the digest, social, the bots inbox, mood2 stages — writes its transcript
into the same project directory, and the newest-mtime rule used to hand the note a probe
run's prompt and answer instead of the day. A conversation has several user turns; a `-p`
run has exactly one, so `memory.handoff_min_user_turns` (3) is the line between them.
"""
import json, subprocess, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "status" / "tools"))
from authcheck import is_auth_error  # type: ignore

HOME = path("paths.home")
OUT = HOME / "memory" / "handoff.md"
TURNS = int(sys.argv[sys.argv.index("--turns") + 1]) if "--turns" in sys.argv else conf("memory.handoff_turns", 60)
MAX_CHARS = int(sys.argv[sys.argv.index("--chars") + 1]) if "--chars" in sys.argv else conf("memory.handoff_max_chars", 6000)
MIN_USER_TURNS = int(conf("memory.handoff_min_user_turns", 3))


def parse_turns(transcript: Path) -> list[str]:
    """The tail of a conversation: user asks and assistant answers, tool noise dropped."""
    turns = []
    with transcript.open(encoding="utf-8") as fh:
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
    return turns


def pick_transcript(files, min_turns=None):
    """Newest-first, the first file with enough real user turns wins; with none qualifying
    the newest is the fallback — a note from the wrong session still beats no note."""
    min_turns = MIN_USER_TURNS if min_turns is None else min_turns
    ordered = sorted(files, key=lambda f: f.stat().st_mtime)
    for f in reversed(ordered):
        turns = parse_turns(f)
        if sum(1 for t in turns if t.startswith("user:")) >= min_turns:
            return f, turns
    return ordered[-1], parse_turns(ordered[-1])


def main() -> None:
    project = path("paths.transcripts") / "-home-ich-claude-home"
    files = list(project.glob("*.jsonl"))
    if not files:
        sys.exit("транскриптів немає")
    latest, turns = pick_transcript(files)

    tail = "\n\n".join(turns[-TURNS:])[-60000:]

    prompt = f"""Ти читаєш хвіст розмови між користувачем і його асистентом Ноосом.
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
        ["claude", "-p", prompt, "--settings", str(HOME / "status" / "digest-settings.json")],
        capture_output=True, text=True, timeout=300)
    note = (res.stdout or "").strip()
    # a failed run's stdout is an error, not a note: on 2026-11-15 the OAuth error went into
    # the next session's system prompt as «Естафета» (t1187). Exiting non-zero makes
    # restart-session.sh keep the conversation instead.
    if res.returncode != 0 or not note or is_auth_error(note):
        sys.exit(f"не вдалося скласти записку (код {res.returncode}): "
                 f"{(note or res.stderr or '')[:200]}")

    OUT.write_text(
        f"<!-- handoff written {datetime.now().isoformat(timespec='seconds')} "
        f"from {latest.stem} -->\n\n{note[:MAX_CHARS]}\n", encoding="utf-8")
    print(f"{OUT} — {len(note)} символів із {len(turns)} реплік")


if __name__ == "__main__":
    main()
