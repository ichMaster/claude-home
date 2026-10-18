# Architecture

## The shape of it

```
                    ┌──────────────── channels ────────────────┐
   terminal  ───────┤ tmux attach                               │
   Telegram  ───────┤ bot plugin (MCP) + notify.sh (Bot API)    │
   claude.ai ───────┤ Remote Control                            │
                    └───────────────────┬──────────────────────┘
                                        │
                           ┌────────────▼────────────┐
                           │   the session (24/7)    │
                           │  persona + CLAUDE.md +  │
                           │     pinned facts        │
                           └───┬──────────┬──────────┘
                               │          │
        ┌──────────────────────┘          └──────────────────────┐
        │                                                         │
┌───────▼────────┐   ┌──────────────┐   ┌─────────────┐   ┌──────▼──────┐
│  probes        │   │   memory     │   │   tasks     │   │   voice     │
│ status/probes  │   │ sessions.db  │   │ tasks.jsonl │   │ ElevenLabs  │
│ JSON contract  │   │ facts/       │   │ + calendar  │   │ Deepgram    │
└───────┬────────┘   └──────────────┘   └─────────────┘   └─────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────┐
│ schedulers (systemd --user): watch · digest · social · youtube ·     │
│ changes · memory index                                               │
└──────────────────────────────────────────────────────────────────────┘
```

## Components

### The session

One long-running Claude Code session in a tmux window, kept alive by a systemd service.
Its system prompt is assembled at start by `start.sh`: `persona.md` plus the output of
`facts.py prompt`. `CLAUDE.md` is loaded as project instructions. Changing any of those
requires a restart to take effect — the prompt is built once.

### Channels

Telegram is the primary one. Inbound messages arrive through the plugin as
`<channel source="telegram">` blocks; replies go out through the plugin's `reply` tool.
Outbound messages that must work **without** a session — scheduled digests, alerts — go
through `notify.sh`, which talks to the Bot API directly with the token from
`.env.telegram`.

Only one process may poll `getUpdates` at a time. This is the single sharpest constraint
in the system: a second session with the Telegram plugin enabled silently steals inbound
messages. Headless runs therefore disable that plugin specifically
(`status/digest-settings.json`) rather than disabling MCP as a whole — because the
claude.ai connectors (Gmail, Calendar) are needed by the same runs.

### Probes

Small scripts under `status/probes/`, each printing one JSON object:

```json
{"id": "loe", "ok": true, "severity": "info|warn|alert",
 "value": {...}, "text": "ready-made line", "ttl": 900}
```

`status/run.sh` executes them with a TTL cache, so two schedulers minutes apart do not
hit the same API twice. `text` is for humans, `value` for comparison with the previous
run, `severity` decides whether anything is sent at all.

Probes have no side effects and may be run at any time. Anything with side effects is
not a probe.

### Schedulers

systemd user timers, each with a different job:

| Timer | Cadence | Job |
|---|---|---|
| `noos-watch` | 15 min | run probes, send only on change or problem |
| `noos-digest` | 08:03, 20:03 | full digest via a headless session |
| `noos-social` | every 2 h, 09–23 | Facebook and LinkedIn, personal items only |
| `noos-youtube` | 18:05 | drain the accumulated video queue, pick a handful |
| `noos-changes` | 23:30 | summary of the day's own changes |
| `claude-memory` | 15 min | incremental transcript indexing |

The digests run as **separate headless sessions** (`claude -p`). They are independent of
the main session's health and cannot block it; the cost is that they do not share its
context.

### Memory

Two layers, deliberately separate:

- **Facts** (`memory/facts/`) — one file per fact, pinned by importance, injected into
  the system prompt at start. Small, hand-curated, about the user.
- **Archive** (`memory/sessions.db`) — every transcript under `~/.claude/projects`,
  indexed into SQLite with FTS5 and multilingual embeddings, searched with reciprocal
  rank fusion. Large, automatic, about everything that was ever said.

The first answers "who is this person"; the second answers "what did we decide in
August".

### Tasks and the plan

`tasks/tasks.jsonl` is an event log — `add`, `done`, `defer`, `cancel`, `edit`, `block`,
`link`, `unlink` — replayed into current state on every read. Nothing is mutated in
place.

A **task** is work to do; an **event** is a slice of time booked for it in the `Noos`
calendar. One task may own several events. The link between them lives in the log, not
in the calendar, because the calendar is reachable only through the connector while the
log is always local.

Three levels of definiteness: a `due` date, a `period` ("this weekend"), or nothing
(backlog). Separately, a `block` flag decides whether time is reserved at all. Tasks
with a date but no block are mirrored as all-day events marked `☐`, closed ones become
`☑`.

### Voice

ElevenLabs for synthesis, Deepgram `nova-3` for recognition, ogg/opus for Telegram.
Every voice reply is duplicated as text, and recognized speech is quoted back so a
misheard word can be corrected. Numbers are spelled out before synthesis
(`status/uk_num.py`), links and emoji stripped.

### Change log

A `PostToolUse` hook (`changelog/hook.py`) appends one line per mutating tool call to
`changelog/YYYY-MM-DD.jsonl`. Reads are not logged. The files carry `chattr +a`, so even
the assistant cannot rewrite them; corrections are new lines.

### Configuration

`config.json` holds shared defaults and is committed; `config.local.json` holds
person-specific values, is git-ignored and merged over it key by key. Code reads both
through `noosconf.py` (`conf()` / `path()`); shell scripts through `config.sh`. No magic
numbers or hardcoded paths in scripts.

## Data flows

**Inbound message:** Telegram → plugin → session → (probe / memory / tool) → `reply`
with text plus voice.

**Scheduled digest:** timer → headless session → probes and connectors → `notify.sh` →
Telegram. No dependency on the main session.

**New task:** chat or `/task` → `store.py add` → event appended → `open.md` regenerated
→ optionally an event created in the `Noos` calendar → `store.py link`.

**Recall:** question → `memory/search.sh` → hybrid search over the archive → fragments
with date, project and session → answer.

## Constraints learned the hard way

- Two sessions polling `getUpdates` lose each other's messages (2026-10-17).
- `--strict-mcp-config` with an empty server list removes the claude.ai connectors too,
  which silently strips Gmail and Calendar from the digest.
- A probe named after a stdlib module (`calendar.py`) shadows it and breaks `urllib`.
  The file is `cal.py`.
- In `.gitignore`, a comment on the same line as a pattern becomes part of the pattern,
  and the rule stops working without a word of warning.
- Deepgram `nova-2` mangles Ukrainian proper nouns; `nova-3` does not.
- Six hundred subscription feeds cannot be polled on every run: the YouTube probe walks
  a rotating window and accumulates findings for the daily digest.
