# Architecture — Noos

## Overview

Two independent axes. **The assistant's senses** grow: the terminal and Telegram → probes
and digests → memory of every past conversation → tasks and a calendar → feeds
(YouTube, social) → operations with side effects. **The interfaces** grow separately: a
tmux session, then Telegram, then Remote Control, and from v5 a local **admin panel**.
They are bound by **files on disk**, which are independent of any interface: the
terminal, the bot, and the browser are three clients of one state.

The second invariant is **the schedule is not the session**. Everything that must happen
whether or not the session is alive — digests, alerts, indexing — runs as a systemd user
timer, either as a plain script or as a short-lived headless session. The long-running
session is a participant, not a dependency.

## Components

- **Session.** One `claude` process in a tmux window, kept alive by the `claude-home`
  systemd service and an inner restart loop. Its system prompt is assembled at start by
  `start.sh` from `persona.md` plus `facts.py prompt`; `CLAUDE.md` is loaded as project
  instructions. **Resumes the previous conversation by default** (`--continue`);
  `restart-clean.sh` drops a one-shot `.fresh` flag for an empty start. Changing the
  persona or the facts requires a restart — the prompt is built once.

- **Channels.** **Telegram** is primary: inbound messages arrive through the plugin as
  `<channel source="telegram">`, replies go out through its `reply` tool. **`notify.sh`**
  is the session-free path: it talks to the Bot API directly with the token from
  `.env.telegram`, so a timer can deliver a message with no session at all. **Terminal**
  (`tmux attach`) and **Remote Control** (claude.ai, session `home`) are the other two.
  Exactly one process may poll `getUpdates`; this is the sharpest constraint in the
  system (§Constraints).

- **Probes** (`status/probes/`). Each prints one JSON object and has no side effects:
  `{id, ok, severity, value, text, ttl}`. `status/run.sh` executes them behind a TTL
  cache, so two schedulers minutes apart do not hit the same API twice. `text` is for
  humans, `value` for comparison with the previous run, `severity` decides whether
  anything is sent at all. Adding a source of truth means adding one file.

- **Watcher** (`status/watch.py`, every 15 min). Runs the fast probes and compares a
  per-probe **signature** against the previous run: `alert` is sent on every change and
  repeated at most every three hours, `warn` only when the signature changes, `info`
  stays silent, a return to normal is reported once. This is where "silence is the
  default" is implemented.

- **Scenarios.** A prompt file executed by a **headless session** (`claude -p`) on a
  timer: `digest-prompt.md` (08:03, 20:03), `social-prompt.md` (every two hours),
  `youtube-prompt.md` (18:05). They read probes and connectors, compose text, and send
  it through `notify.sh`. Being separate sessions, they cannot block the main one; the
  cost is that they do not share its context. Each runs with the Telegram plugin
  disabled and the claude.ai connectors enabled (§Constraints).

- **Memory.** Two layers, deliberately separate. **Facts** (`memory/facts/`) — one file
  per fact, pinned 0–2, injected into the system prompt at start; small and
  hand-curated. **Archive** (`memory/sessions.db`) — every transcript under
  `~/.claude/projects`, indexed incrementally by file offset into SQLite with FTS5 and
  multilingual embeddings, searched by reciprocal rank fusion. The first answers "who is
  this person", the second "what did we decide in August".

- **Tasks and the plan.** `tasks/tasks.jsonl` is an append-only event log — `add`,
  `done`, `defer`, `cancel`, `edit`, `block`, `link`, `unlink` — replayed into state on
  every read; `tasks/open.md` is a derived human view. A **task** is work; an **event**
  is time booked for it in the `Noos` calendar. The link lives in the log rather than in
  the calendar, because the log is always local while the calendar is reachable only
  through a connector.

- **Voice.** ElevenLabs for synthesis, Deepgram `nova-3` for recognition, ogg/opus for
  Telegram. Every voice reply is duplicated as text and recognized speech is quoted back,
  so a misheard word can be corrected. Numbers are spelled out before synthesis
  (`status/uk_num.py`); links and emoji are stripped.

- **Change log.** A `PostToolUse` hook appends one line per mutating tool call to
  `changelog/YYYY-MM-DD.jsonl`; reads are not logged. Daily files carry `chattr +a`, so
  not even the assistant can rewrite them.

- **Configuration.** `config.json` holds shared defaults and is committed;
  `config.local.json` holds person-specific values, is git-ignored, and is merged over it
  key by key. Python reads both through `noosconf.py` (`conf()` / `path()`), shell
  through `config.sh`. No magic numbers or hardcoded paths in scripts.

- **Panel (from v5).** A local web process on `127.0.0.1:8091` that reads and edits the
  same files: the assembled prompt, facts, scenarios, schedule, permissions, task board.
  It has **no store of its own** and writes every change to the change log, so the panel
  and the session can never diverge. Details in [features/ADMIN-PANEL.md](features/ADMIN-PANEL.md).

## Contracts

**Probe → anything.** One JSON object on stdout:
`{"id", "ok", "severity": "info|warn|alert", "value": {...}, "text": "…", "ttl": seconds}`.
A probe that cannot answer still prints an object with `ok: false` and a human `text`;
it never exits non-zero and never writes to stderr in anger.

**Task log line.** `{"ts", "op", "id", …fields}` appended to `tasks.jsonl`. State is the
replay; no reader mutates the file.

**Change log line.** `{"ts", "kind", "target", "detail", "session", "cwd"}`.

**Config access.** `conf("dotted.key", default)` and `path("dotted.key")`. Code never
reads `config.json` directly, so the local overlay always applies.

## State on disk

```
memory/facts/*.md            pinned facts, one per file
memory/sessions.db           transcript index (FTS5 + embeddings)
tasks/tasks.jsonl            append-only task events
tasks/open.md                derived view
status/state/mail.json       last seen UID
status/state/youtube.json    seen video ids, rotation cursor, pending queue
status/state/watch.json      per-probe signatures and last-sent times
status/cache/*.json          probe answers within their TTL
changelog/*.jsonl            append-only, chattr +a
config.json / config.local.json
.env.telegram / .env.voice / .env.news   mode 600, never in git
```

## Security and access

Secrets live only in `.env.*` files with mode 600 and are read by scripts, never by an
interface. The panel may show that a key exists; it may never show or edit one.
Permission changes, pairing, and anything touching the allowlist happen **from the
terminal only** — a message in a chat does not prove who sent it.

Outward actions are ranked: sending mail and creating calendar events are allowed only
with an explicit instruction; editing the owner's own events is never allowed; deleting
data requires a human sentence. From v5 these rules become switches in the panel rather
than prose in `CLAUDE.md`.

## Constraints learned the hard way

- **One `getUpdates` poller.** A second session with the Telegram plugin enabled
  silently steals inbound messages. Headless runs disable that plugin specifically.
- **`--strict-mcp-config` removes the connectors too.** Killing all MCP to protect the
  bot also strips Gmail and Calendar, which the digest needs. Disable the plugin, not the
  protocol.
- **A probe must not be named after a stdlib module.** `calendar.py` shadowed `calendar`
  and broke `urllib`; the file is `cal.py`.
- **`.gitignore` has no inline comments.** A comment after a pattern becomes part of the
  pattern, and the rule silently stops working.
- **Deepgram `nova-2` mangles Ukrainian proper nouns**; `nova-3` does not.
- **Six hundred feeds cannot be polled per run.** The YouTube probe walks a rotating
  window and accumulates findings for the daily digest.
- **Context is not memory.** The session compacts itself when full; anything that must
  survive the day belongs in a file, not in the conversation.
