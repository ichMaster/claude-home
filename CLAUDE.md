# Noos — the always-on assistant

Persona (name, character, tone, the rule about asking when confidence is low):
`persona.md`. It applies both in the terminal and in Telegram; `start.sh` passes it
via `--append-system-prompt`.

This session runs 24/7 on this machine (tmux session `claude`, systemd service
`claude-home`). Three ways to reach it: the terminal (`tmux attach -t claude`),
Claude desktop / claude.ai/code (Remote Control, session "home"), and the Telegram bot.

- **IMPORTANT:** Telegram messages arrive as `<channel source="telegram" chat_id=...>`.
  The user in Telegram does NOT see your terminal output — every answer to such a
  message MUST go out through the `reply` tool (telegram) with the same `chat_id`.
  Short, in Ukrainian.
- Long results go to files here; send the path or the file itself.

**Language rule:** documentation, code comments and commit messages are English.
Conversation with the user is Ukrainian; so are user-facing strings (probe output,
digests, Telegram replies) and the Ukrainian CLI flags of `tasks/store.py`.

## Voice (Telegram)

Keys: `~/claude-home/.env.voice` (mode 600) — ElevenLabs + Deepgram, inherited from the
lumi project. Virtualenv: `~/claude-home/.venv-voice` (built with `virtualenv`, because
`python3-venv` is not installed).

**Main path (fast):**
- Recognize: `./voice/dg_stt.sh <file.oga> uk` — Deepgram `nova-3`, ~1 s per 15 s of
  audio. `nova-2` mangles Ukrainian proper nouns — do not use it.
- Synthesize: `./voice/reply.sh "text" <out.ogg>` — one step: ElevenLabs (voice
  **HAL-UA**, `$ELEVENLABS_VOICE_ID` from `.env.voice`) → `.ogg` ready for `reply`.
  The muffle filter is **off** by default (the clean voice sounds better);
  `voice/muffle.py` is still there — enable it with a third argument or
  `NOOS_MUFFLE=light|medium|heavy`. Voice, speed and muffling are overridable via env:
  `ELEVENLABS_VOICE_ID`, `ELEVENLABS_SPEED` (0.7-1.2), `ELEVENLABS_STABILITY`,
  `NOOS_MUFFLE`.

**Fallback:** there is no local one any more — whisper and its model were deleted on
2026-10-17 as unused (1.9 GB freed). To bring offline recognition back:
`.venv-voice/bin/pip install faster-whisper` plus a script around
`WhisperModel("large-v3-turbo", compute_type="int8")`.
`./voice/el_stt.sh <file.oga> ukr` — ElevenLabs Scribe, a backup path in case Deepgram
fails (untested).

- **IMPORTANT:** every voice reply MUST be duplicated as text in the same `reply`, and
  the recognized text quoted back so the user can correct it.
- In text meant for synthesis, avoid Latin script and abbreviations — spell things out
  in Ukrainian words.
- The plugin sends files via `sendDocument`, so audio arrives as a file rather than a
  native voice message.

## Telegram command menu

`telegram/commands.sh` registers the bot menu via `setMyCommands` (`--remove` removes
it). Command names are `[a-z0-9_]` only; descriptions are Ukrainian. A tapped command
arrives as an ordinary message and is handled by the session — so it only works while
the session is alive.

| Command | What to run |
|---|---|
| `/power` | `./status/send.sh loe` |
| `/alarm` | `./status/send.sh alarm` |
| `/weather` | `./status/send.sh weather` |
| `/host` | `./status/send.sh host services` |
| `/status` | `./status/send.sh --title "Стан" loe alarm weather host services` |
| `/mail` | `./status/send.sh mail` |
| `/calendar` | `./status/send.sh cal` |
| `/tasks` | `./status/send.sh tasks` |
| `/task <text>` | `tasks/store.py add "<text>"` — date and period are parsed out of the text |
| `/done <id\|title>` | `tasks/store.py done …` |
| `/plan <id> <when> [min]` | create an event in the `Noos` calendar via the connector → `store.py link` |
| `/unplan <id>` | delete the event via the connector → `store.py unlink` |
| `/today` | today's events from the calendars + `run.sh tasks` |
| `/changes` | `./status/changes-send.sh` |
| `/digest` | `./status/digest-headless.sh вечірній` (or `ранковий`) |

## Memory of past sessions (RAG)

Every transcript under `~/.claude/projects/**/*.jsonl` is indexed into
`memory/sessions.db` (SQLite: FTS5 + `paraphrase-multilingual-MiniLM-L12-v2`
embeddings).

- **Search:** `./memory/search.sh "query" [count]` — hybrid full-text and semantic
  search with reciprocal rank fusion. Returns fragments with date, role, project and
  session. ~2 s per query.
- **When to search:** the user refers to past conversations ("we already set this up",
  "like I asked back then", "what did we decide about…"), or a decision needs to be
  recalled that is not in context. Search instead of saying "I don't remember".
- **Indexing:** automatic, `claude-memory.timer` every 15 min, incremental by file
  offset. Manual: `.venv-voice/bin/python memory/ingest.py`; full rebuild with
  `--rebuild`.
- This does not replace `~/.claude/projects/-home-ich-claude-home/memory/`: that holds
  compact facts about the user, this is the full searchable conversation archive.

## Pinned facts

`memory/facts/` — one file per fact, managed through `memory/facts.py`
(`add --pin 1|2|0`, `list`, `prompt`, `pin`, `rm`). Limits: 100 facts in the store, up
to 25 in the system prompt, up to 240 characters per fact in the prompt.

`start.sh` assembles the prompt as `persona.md` plus the output of `facts.py prompt`, so
pinned facts are available from the first message of a new session. All facts are also
indexed into `memory/sessions.db` (project `факти`), so search finds them.

## Schedulers (systemd --user)

- `noos-watch.timer` — every 15 min, `status/watch.py`: reports only changes and
  problems.
- `noos-digest.timer` — 08:03 and 20:03, `status/digest-headless.sh`: a separate
  headless session (`claude -p`) collects candidates, picks the news itself and sends
  the digest as text and voice. Candidates come from all eight topics; selection is two
  steps: at most 2 items per topic, then rank everything selected and keep exactly 4.
  The `candidates.py --random N` flag remains as an option for manual runs.
- `claude-memory.timer` — every 15 min, transcript indexing.
- `noos-changes.timer` — 23:30, `status/changes-send.sh`: a short summary of the day's
  changes (text only).

**IMPORTANT:** in headless runs disable **the Telegram plugin specifically**, not MCP as
a whole: `--settings status/digest-settings.json` (it holds `enabledPlugins` with
`telegram…: false`). Leave the plugin on and the second session hijacks `getUpdates`,
and the main session loses incoming messages (this happened on 2026-10-17). The
`--mcp-config '{"mcpServers":{}}' --strict-mcp-config` variant is safe too, but it also
strips the claude.ai connectors — verified on 2026-10-17 that without it a headless
session sees Gmail and Calendar, and that is exactly how the digest reads mail and
events.

## Mail (probe `mail`)

`status/probes/mail.py` — what is new in Gmail since the last check. IMAP, headers only,
`BODY.PEEK` (marks nothing as read). Keys live in `.env.gmail` (mode 600, sample in
`.env.gmail.example`): `GMAIL_USER` + `GMAIL_APP_PASSWORD` (a Google app password,
two-factor auth required). State is `status/state/mail.json` (last UID), so "new" means
"was not there at the previous check".

Sorting: `status/mail-rules.json` (optional) overrides the `шум` (noise) and `важливе`
(important) lists; everything else is "ordinary". Important raises severity to `warn`,
so the watcher reports it.

The Gmail connector over claude.ai (MCP) works only in an interactive session — the
headless digest cannot use it, which is why the probe goes through its own IMAP.

## Calendar (probe `cal`)

`status/probes/cal.py` — events from now until the end of the next day (the argument is
how many days ahead, default 1). The source is the "secret address in iCal format" from
Google Calendar settings, one line per calendar in `.env.calendar` (sample in
`.env.calendar.example`):
`CAL_особистий=https://calendar.google.com/calendar/ical/.../basic.ics`.

Why this and not the connector: iCal is plain HTTPS without OAuth, so it works headless
too. Recurring events are expanded through RRULE (`python-dateutil`, installed into
`.venv-voice`); cancelled ones (`STATUS:CANCELLED`) and `EXDATE` are dropped.

The file is deliberately `cal.py` and not `calendar.py`: the latter shadows the stdlib
`calendar` module and breaks `urllib`.

## Tasks (tasks/)

`tasks/tasks.jsonl` — an event log (add / done / cancel / defer / edit),
**append-only**; state is rebuilt by replaying it. `tasks/open.md` is a derived
human-readable view, regenerated automatically. The `Noos` calendar, the sleep window and the
planning rules live in `config.json` (section `tasks`); the calendar id itself is in
`config.local.json`, which is git-ignored.

Management: `.venv-voice/bin/python tasks/store.py` —
`add "text [date]" [--project x] [--min 90] [--deep]`, `list [--all]`,
`done <id|part of title>`, `defer <id> "завтра"`, `cancel <id>`, `md`. Dates are parsed
out of Ukrainian text ("завтра", "до 20 жовтня", "у п'ятницю", "через 3 дні", "18.10")
and removed from the title.

The `tasks` probe reports overdue, today and this week; `severity: warn` when something
is overdue or due today, so the watcher speaks up. The digest has a "Задачі" section.

**A task and an event are different things.** A task can own zero, one or several events
in the `Noos` calendar; an event is a booked slice of time for a task, not the task
itself. The link lives in the same log as `link` / `unlink` events (`event`, `start`,
`end`, `calendar`), because the calendar itself is reachable only through the connector,
not from `store.py`. The order of operations: create the event via the connector →
immediately `store.py link <id> <event_id> <start> <end>`; delete the event → `unlink`.
Closing a task does not remove its future events — that is a separate step.

**Mirroring as all-day events.** A task with a date or a period but without a time block
also goes into the `Noos` calendar — as an all-day event marked `☐` with
`availability=FREE` (it does not block time). A period becomes a multi-day event. A
backlog item without a date does not go to the calendar, and neither do Noos's own
technical tasks. Title markers: `☐` open, `☑` done — a closed task is not removed from
the calendar but renamed, so the day shows the facts and not only the plan.

**Not everything goes to the calendar.** A task has three levels of definiteness:
`due` — a concrete deadline date; `period` — a kind and a range ("вихідні 24.10-25.10",
"тиждень 18.10-25.10", "місяць"); nothing — backlog. Separately there is the `block`
flag: only tasks with `block: true` (marker 📌, flag `--block`, or
`store.py block <id> on`) get a time block in the calendar. The rest live as a list and
show up in the digest, but no time is reserved for them.

Planning (step 2, not built yet): blocks go **only** into the `Noos` calendar (id in
`config.local.json`), at any time except the 00:00–08:00 sleep window, routing around
power outages from the `loe` probe. The user's own events are never edited.

## Configuration

`config.json` — shared settings: paths, probe sources and TTLs, memory limits, digest
and task rules. Committed, holds neutral defaults.

`config.local.json` — machine- and person-specific values (user name, calendar id).
Git-ignored, mode 600, merged over `config.json` key by key.

Read it from Python:

```python
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # parents[2] from status/probes/
from noosconf import conf, path
conf("probes.loe.queue")      # value, with a default as the second argument
path("memory.db")             # absolute Path, ~ expanded and resolved against the repo root
```

From shell: `. ./config.sh; queue=$(conf probes.loe.queue)`.

**No magic numbers or paths in code.** Anything a person might want to change —
limits, URLs, TTLs, cities, queue numbers, windows — belongs in `config.json`; the
code reads it through `noosconf`. Environment variables still override where they
already did (`LOE_CHERGA`, `ALARM_REGION`, `ELEVENLABS_VOICE_ID`).

## Git

Repository: `git@github.com:ichMaster/claude-home.git`, branch `main`, **public**.

- **Commit messages in English only.** Documentation, README and code comments are
  English as well; Ukrainian stays in conversation and in user-facing output.
- Every commit to a public repository is a publication. Do not commit or push without an
  explicit request from the user.
- Before pushing, scan what is going out for secrets:
  `git grep -nIE "(sk-[A-Za-z0-9]{20,}|bot[0-9]{6,}:|@gmail\.com|AIza[0-9A-Za-z_-]{25,})" HEAD -- .`
- Personal and secret material never enters the repository — the list is in
  `.gitignore`, and it is verified with `git status --ignored`, not by eye.

## Change log (changelog/)

`changelog/YYYY-MM-DD.jsonl` — one line per action that changed something. It is filled
by the PostToolUse hook `changelog/hook.py` (declared in `.claude/settings.json`,
matcher `Write|Edit|MultiEdit|NotebookEdit|Bash`). Reads are not logged: this is a log of
changes, not of lookups. A record holds `ts`, `kind`, `target`, `detail`, `session`,
`cwd`.

**IMPORTANT:** the `changelog/` directory may only be appended to and read. Do not
delete, rewrite or "clean up" lines — not even test or mistaken ones. Corrections go in
as a new line, never as an edit of an old one.

This is enforced with `chattr +a` on the daily files (applied as root on 2026-10-17).
New daily files do not inherit the attribute — `changelog/seal.sh` applies it to all
`*.jsonl`; the installation instructions for root are in the script header.

- Daily summary: `.venv-voice/bin/python status/probes/changes.py [YYYY-MM-DD]`
  (probe `changes`, same contract as the rest of `status/probes/`).
- Send the summary to Telegram: `status/changes-send.sh [YYYY-MM-DD]` — the
  `noos-changes.timer` does this daily at 23:30 (end of day).
- The hook is read at session start. After changing `.claude/settings.json` you need
  `/hooks` or a session restart (`./restart-session.sh`), otherwise it is not active.
