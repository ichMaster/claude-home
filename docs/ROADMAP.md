# Roadmap — Noos

Versions are numbered from 0; phases inside a version are numbered `vA.B` (A = version,
B = phase), e.g. `v5.2`. A version is self-contained: after it, the assistant is useful
in a new way, not merely closer to being useful. Phases are ordered by dependency.

Versions v0–v4 are **done** and describe what exists today; v5 onwards is the plan.

---

## v0 — The session that stays (done)

**Goal:** an assistant that is reachable at any hour and survives reboots.

**Description.** One Claude Code session under tmux and systemd, with a persona passed
through `--append-system-prompt` and project instructions in `CLAUDE.md`. Telegram as
the first channel, in both directions, with voice. Session-free delivery through
`notify.sh` so a timer can speak without the session.

**Done:** the service restarts after a crash and a reboot; a Telegram message reaches
the session and is answered by voice plus text; `./restart.sh` keeps the conversation,
`./restart-clean.sh` drops it.

## v1 — Senses (done)

**Goal:** the state of the few things that matter, without opening three apps.

**Description.** The probe contract and the TTL cache; probes for power outages, air
alerts, weather, host, services, news by topic. The watcher that compares signatures and
reports only changes. Digests at 08:03 and 20:03 assembled by a headless session that
picks the news itself.

**Done:** a changed outage schedule arrives within 15 minutes; an unchanged one is never
mentioned; the digest contains four news items chosen from eight topics.

## v2 — Memory (done)

**Goal:** stop re-explaining who the owner is and what was decided.

**Description.** Pinned facts injected into the system prompt at start, and the full
transcript archive indexed into SQLite with FTS5 plus embeddings, searched by reciprocal
rank fusion. Indexing runs incrementally every fifteen minutes.

**Done:** "what did we decide about X" is answered from the archive in about two
seconds; a new session knows the owner from the first message.

## v3 — Tasks and the plan (done up to v3.2)

### v3.1 Task store (done)
Append-only event log, Ukrainian date parsing out of free text, derived `open.md`, a
`tasks` probe, and a digest section.

### v3.2 Calendar (done)
A separate `Noos` calendar. Tasks with a time block become events; tasks with only a
date or a period are mirrored as all-day `☐` entries and renamed `☑` when closed. One
task may own several events, linked through the log. The owner's calendars are read-only.

### v3.3 Planner (next, see v5.4 ordering)
Automatic block layout: free slots from the calendars, outage windows avoided, deep work
in large blocks, nothing denser than four hours a day, blocks moved by hand respected.

## v4 — Feeds (done)

**Goal:** the outside world that is worth a glance, without becoming a feed.

**Description.** YouTube over per-channel RSS: no API key, a rotating poll across 600+
subscriptions, Shorts skipped, findings accumulated into a queue that the 18:05 digest
drains. Facebook and LinkedIn through the Gmail connector, personal items only, checked
every two hours and silent by default.

**Done:** the YouTube digest arrives once a day with four to six videos; the social
check has sent nothing on a quiet day.

---

## v5 — The panel

**Goal:** make the assistant's own configuration visible and editable without a
terminal, while keeping files the single source of truth.

**Depends on:** v0–v4. Full functional and design spec in
[features/ADMIN-PANEL.md](features/ADMIN-PANEL.md).

### v5.1 Pulse and prompt

**Goal:** see what the session actually reads and what the schedule actually did.

**Description.** A single Python process on `127.0.0.1:8091`, no build step, server-side
HTML. Two screens: **Prompt** — the assembled system prompt exactly as `start.sh` builds
it, with the facts that fit and the ones cut by the limit; **Pulse** — probes with their
last answer and severity, timers with next and last run, the YouTube queue size, the
last twenty change-log lines.

**Tasks:** read-only endpoints over `config`, `status/cache`, `status/state`,
`systemctl --user list-timers`, `changelog`; one HTML template; a systemd unit for the
panel itself.

**DoD:** the panel shows a stale probe and a failed timer without the owner opening a
terminal; nothing in it can change state yet.

**Tests:** a probe cache that is older than its TTL is rendered as stale; a unit in
`failed` state is rendered as failed; the prompt rendering matches `start.sh` byte for
byte.

### v5.2 Scenarios

**Goal:** edit and try the scheduled prompts where their output is visible.

**Description.** `digest-prompt.md`, `social-prompt.md`, `youtube-prompt.md` in an
editor, with **Run now** and **Dry run** (compose but do not send), the output of the
last three runs underneath, and a diff against the committed version.

**Tasks:** execute a scenario in a subprocess with the same settings file the timer
uses; stream the output; store the last runs under `status/state/runs/`.

**DoD:** a wording change in the digest prompt can be tried and reverted in under a
minute without touching the terminal.

**Tests:** a dry run sends nothing to Telegram; a failed run is shown with its stderr;
an edit is written to the change log.

### v5.3 Memory

**Goal:** curate what the assistant remembers.

**Description.** The facts table — text, pin level, date, which ones reached the prompt
and which were cut — with add, edit, re-pin, delete. Archive statistics and a search
box that runs the same hybrid query the session runs.

**DoD:** a stale fact can be removed and the prompt preview updates immediately, with a
"restart required" banner.

**Tests:** deleting a fact appends to the change log; the search box and
`memory/search.sh` return the same first five results.

### v5.4 Rules

**Goal:** turn prose rules into switches.

**Description.** Configuration as a form rather than JSON: probe TTLs, planning window,
sleep hours, mail and LinkedIn filters, YouTube channels with search, enable/disable and
a priority flag. Permissions as explicit toggles: send mail — only with confirmation;
create events — free; edit the owner's events — never. Timers with their schedules.

**DoD:** adding a YouTube channel to `priority`, changing the digest time, and
tightening a permission all happen in the browser and are visible in the change log.

**Tests:** a schedule change rewrites the unit and reloads systemd; an invalid cron
expression is rejected before writing; `config.local.json` keeps its mode 600.

### v5.5 Tasks board

**Goal:** the one view chat is bad at.

**Description.** Backlog / today / period / closed as columns, with drag to change a
date, a checkbox to close, and the 📌 flag for a time block. The calendar stays the
source of truth for events; the board shows them and can unlink.

**DoD:** closing a task on the board renames its all-day event `☐ → ☑` in the calendar.

---

## v6 — Operations and new channels

### v6.1 Operations (`ops/`)
Actions with side effects as first-class citizens: restart a container, free disk space,
rebuild the index. Only entries flagged `auto: true` may run on a timer; everything else
needs confirmation; every run appends to `ops/log.jsonl`.

### v6.2 Mail without the connector
Google OAuth with a Gmail scope so the mail probe works headless instead of depending on
the interactive session. App passwords are unavailable on this account (passkey-only
sign-in), which is why this is a version and not an afternoon.

### v6.3 Telegram over MTProto
A local MCP server on Telethon for contacts, dialogs, history, and search — none of
which the Bot API provides. The session file is as sensitive as the account itself, so
it stays in `.secrets/`, mode 600, and authorization happens in the terminal.

### v6.4 Weekly review
Sunday evening: what was done, what stalled, what to drop — generated from the task log
and the change log, answered by one voice reply.

---

## Deliberately not doing

- **Meta feeds and Messenger.** The APIs were removed; the only route left is an
  unofficial client that violates the terms, breaks weekly, and risks the account.
  Facebook stays as e-mail notifications.
- **YouTube Data API.** Per-channel RSS already answers "what is new" without OAuth or
  quotas.
- **Multi-user, authentication, tenancy.** One machine, one person; the panel listens on
  localhost and is reached over SSH or Tailscale.
- **Secrets in any interface but the terminal.** The panel may show that a key exists,
  never what it is.
- **A chat window in the panel.** Telegram and the terminal already do that; duplicating
  it would create a second place where context lives.
