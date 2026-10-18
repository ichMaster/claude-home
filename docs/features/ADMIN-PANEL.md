# Admin panel — functionality and design

Status: specification, nothing built. Target: v5 of [ROADMAP.md](../ROADMAP.md).

## Why a panel at all

Chat is good at intent ("plan the aquarium for tomorrow evening") and bad at **lists,
tables, and state**. Three things in Noos are now painful precisely because they are
lists: 603 YouTube channels, the filters for mail and social, and the question "what did
the schedule actually do while I slept". A panel exists for those, and for one more
thing chat cannot do at all — **showing the assistant to itself**: the exact system
prompt it wakes up with.

Everything the panel does could be done by typing. The panel is not a new capability;
it is the same capabilities with a short feedback loop.

## The one hard rule

**The panel has no store of its own.** It reads and writes exactly the files the session
reads: `config.json`, `config.local.json`, `persona.md`, `CLAUDE.md`, the scenario
prompts, `memory/facts/`, `tasks/tasks.jsonl`, systemd units. Every write appends to
`changelog/` through the same hook path the assistant uses.

The consequence to keep in mind: **a panel edit and an assistant edit are the same kind
of event**, so they cannot drift apart, and a week later it is still visible who changed
what.

## Screens

### 1. Pulse (home)

The answer to "is it alive and did anything happen".

- **Probes**: id, severity dot, last answer (`text`, one line), age against TTL, a
  *Run* button. A probe whose cache is older than its TTL is rendered stale rather than
  silently old.
- **Timers**: unit, schedule, next run, last run and whether it succeeded, an
  enable/disable switch.
- **Queues**: YouTube pending count, mail last UID, watcher signatures that are
  currently non-`info`.
- **Recent changes**: last twenty lines of the change log, newest first.

Nothing on this screen is a form; it is a status board that refreshes itself every
thirty seconds.

### 2. Prompt

The screen that justifies the project.

- The **assembled system prompt**, exactly as `start.sh` builds it: `persona.md` plus
  `facts.py prompt`, with a character count and the model's context budget for scale.
- `persona.md` and `CLAUDE.md` in an editor with a diff against the committed version.
- A **"restart required"** banner the moment either file differs from what the running
  session loaded, with the two restart buttons (keep conversation / clean).
- Facts that were **cut** by the prompt limit, shown greyed under the ones that fit —
  the single most surprising piece of state in the system today.

### 3. Scenarios

Where the scheduled prompts live.

- The three prompt files in an editor, each with: **Run now**, **Dry run** (compose and
  show, send nothing), the schedule that triggers it, and the output of the last three
  runs with timing and exit status.
- Output is stored under `status/state/runs/<scenario>/<timestamp>.txt` so the panel can
  show history without a database.

### 4. Memory

- **Facts**: table of text, pin level, date added, tags; inline edit, re-pin by dragging
  between levels, delete with a confirmation. A counter against both limits (100 stored,
  25 in the prompt).
- **Archive**: index size, last indexing run, a *Reindex* button, and a search box that
  runs the same hybrid query as `memory/search.sh`, showing date, role, project, and
  fragment.

### 5. Sources

- **YouTube channels**: 603 rows with search, sort by recent activity, a disable switch,
  a priority star (polled every run instead of in rotation), and a *Remove dead* action
  for channels that answer 404.
- **Mail and social filters**: the noise/important lists for mail, the four personal
  LinkedIn senders and the noise prefixes, with a *Test on the last 24 h* button that
  shows what the current filter would have kept.
- **News topics**: name, description, query, sources, limit.

### 6. Rules

- **Configuration as a form**: TTLs, planning window, sleep hours, digest item counts,
  voice settings. Each field shows its default from `config.json` and whether
  `config.local.json` overrides it.
- **Permissions as switches**, replacing prose in `CLAUDE.md`: send mail — *ask* /
  *never* / *free*; create calendar events — *free*; edit the owner's events — *never*;
  delete files — *ask*. The panel writes them into `config.json`; the session reads them
  as part of its instructions.
- **Schedule**: the five timers with editable times; saving rewrites the unit and runs
  `daemon-reload`.
- **Keys**: a read-only list — `.env.voice` present, `.env.gmail` missing. Never a
  value, never an input field.

### 7. Tasks

Backlog / today / period / closed as four columns. Drag to change a date, checkbox to
close, 📌 to request a time block. Events are shown under their task with their calendar
time; unlinking removes the event. The calendar remains the source of truth for events;
the board never invents one.

## Design

**Visual language.** The same one the assistant speaks in: dark, quiet, dense.
Charcoal background, one amber accent for anything that needs attention, a blue-grey for
links. No cards with shadows, no rounded corporate boxes — thin rules between rows, a
monospace face for ids, times, and anything the user might copy. Density over
whitespace: this is an instrument panel, not a landing page.

**Status colour is earned, not decorative.** Grey is normal, amber is `warn`, red is
`alert`, and nothing else is coloured. If every row is coloured, the board stops working
— the same reason the watcher stays silent by default.

**Layout.** A fixed left rail with the seven screens, content in a single column capped
at ~1100 px. Every screen answers one question; no dashboard that mixes four.

**Interaction.** Server-rendered HTML with small HTMX-style fragment swaps for the live
bits (probe rows, run output). No client framework, no build step, no CDN — the panel
must work on a machine with no internet, because its job is to be the thing that still
works.

**Editing.** Textareas with a monospace face and a diff view, not a rich editor. Save is
explicit; a dirty buffer is marked. Any edit that needs a restart says so at the moment
of saving, not later.

**Mobile.** The Pulse screen is readable on a phone; the rest is not a priority. A phone
already has Telegram, which is the better interface for intent.

## Technical shape

- One Python process, standard library plus the existing venv; a single `panel/` package
  with `server.py`, templates, and one CSS file.
- Listens on `127.0.0.1:8091` (8090 belongs to the matrix-agora panel). Reached over an
  SSH tunnel or Tailscale. **No authentication**, because it is not exposed; if it ever
  needs to be, that is a version of its own and not a checkbox.
- A systemd user unit `noos-panel.service`, restart on failure, no timer.
- Writes go through the same helpers the scripts use (`noosconf`, `store.py`,
  `facts.py`), never by hand-editing JSON — so validation lives in one place.
- The panel never calls the model. Everything intelligent is either a script or a
  scenario run in a headless session.

## Out of scope

- Chat with the assistant: Telegram and the terminal already do it.
- Secret values in any form.
- Remote access, accounts, roles.
- Charts and analytics beyond token spend per day; a graph is not an answer.
- Editing the change log or the task log by hand — both are append-only by design.
