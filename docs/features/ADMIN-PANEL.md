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

Where the scheduled prompts live — the ones that belong to no single channel: the digest,
social, the handoff note, the nightly code review. The horoscope and the content bot each
have a screen of their own (4 and 5), because each is a pipeline with its own state,
history and voice, and folding them into a generic prompt list hid exactly the parts worth
looking at.

- Each prompt file in an editor, with: **Run now**, **Dry run** (compose and show, send
  nothing), the schedule that triggers it, and the output of the last three runs with
  timing and exit status.
- Output is stored under `status/state/runs/<scenario>/<timestamp>.txt` so the panel can
  show history without a database.

### 4. Zirka — the horoscope

The forecast is seventeen model calls and four accumulating stores, and today the only way
to see inside it is to read `mood.log` by hand. This screen is that log with a shape.

- **Today's reading** as it was sent: the five blocks, with the character count against
  each block's budget and whether the compression pass had to run.
- **The pipeline**, one row per stage — facts, houses, Moon, background, weighing, draft,
  review, summary, biorhythms — each with its duration, the model it used, and its output
  behind a fold. A failed stage is red and says what `--resume` would pick up.
- **The computed facts**, straight from `astro.py`: transits with their windows (in orb
  from, exact, how many days), the day's focus, the houses table. No model involved, so
  this is the ground truth every claim above has to rest on.
- **Calibration**: the rules in force, each with the day it was learned from, and the
  feedback log beside them — what he said about a day next to what was promised. This is
  the pair that makes a rule arguable.
- **References from the real astrologer**: the list with date, author and period, and —
  the part that earns the screen — **a textarea to paste a new one**. A long reading does
  not survive Telegram (a long paste becomes a file, a forward can be lost); a textarea
  has no such limit. Paste, pick the date, save, and the distillation runs on the spot with
  its new `ПРАВИЛО:` lines shown.
- **Actions**: run the forecast, dry run, `--resume` the summary, recompute the facts,
  calibrate a chosen day, ask the evening question now.
- **Voice**: Зоря's profile — voice, model, stability, style, tempo — with a *Say this*
  box for testing a line before a morning depends on it.
- **The chart**: the natal positions, houses and rulers, plus the written portrait; and the
  other subjects (`astro.subjects`) with their own charts and their own logs.

### 5. Bruno — news and video

The same idea for the content channel: what was chosen, out of what, and why.

- **What was sent**: the last digests' news sections and the evening video picks, each item
  with its link and the date it went out.
- **What was dropped as a repeat**: the candidates `news_seen.py` filtered, with the reason
  — same link, or the headline overlap and the earlier story it matched. The dedup is the
  piece most likely to be wrong, and it is currently invisible.
- **The subscription archive**: how many videos, what span of dates it actually covers, and
  a search box running the same query `search.py` serves Bruno — with the standing caveat
  that the archive is candidates by recency and the choosing is the model's, not a score.
- **Topics**: name, description, query, sources, limit, with a *Collect now* that shows the
  candidate list without sending anything.
- **The chat**: the last turns in Bruno's own chat, the hourly cap, and the dropped log with
  the shape of each dropped message — which is how a mis-typed document or a photo gets
  diagnosed without asking the owner what he sent.
- **Prompts**: `bruno.md`, `intent.md` and the digest's news section, in an editor beside
  the output they produced.
- **Voice**: Бруно's profile and the same *Say this* box.

The 603 channels stay on **Sources** — they are a list to maintain, not a pipeline to watch
— with a link from here.

### 6. Memory

- **Facts**: table of text, pin level, date added, tags; inline edit, re-pin by dragging
  between levels, delete with a confirmation. A counter against both limits (100 stored,
  25 in the prompt).
- **Archive**: index size, last indexing run, a *Reindex* button, and a search box that
  runs the same hybrid query as `memory/search.sh`, showing date, role, project, and
  fragment.

### 7. Sources

- **YouTube channels**: 603 rows with search, sort by recent activity, a disable switch,
  a priority star (polled every run instead of in rotation), and a *Remove dead* action
  for channels that answer 404.
- **Mail and social filters**: the noise/important lists for mail, the four personal
  LinkedIn senders and the noise prefixes, with a *Test on the last 24 h* button that
  shows what the current filter would have kept.
- **News topics**: name, description, query, sources, limit.

### 8. Rules

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

### 9. Tasks

Backlog / today / period / closed as four columns. Drag to change a date, checkbox to
close, 📌 to request a time block. Events are shown under their task with their calendar
time; unlinking removes the event. The calendar remains the source of truth for events;
the board never invents one.

### 10. Changes — what was built and how it was reviewed

The development process (CLAUDE.md § Development process) says: no change without a task, no
task without a spec and tests, every commit naming its task id, a security reading of every
staged diff, and a nightly self-review. All of that is true and none of it is *visible* — the
verdicts live in chat messages that scroll away. This screen is the record.

- **Commits**, newest first: hash, date, subject, the task id parsed out of it, the files
  touched, and whether the commit is still local or already on the public remote. A commit
  with no task id is flagged, because the process says there should not be one.
- **Behind each commit**, one click away: the task's title and state, its spec
  (`tasks/specs/<id>.md`) with the test cases, the tests that were added, and the suite's
  result at that commit.
- **The commit-time security reading.** Today its verdict is spoken once and lost; the panel
  needs it stored, so the reading is written to `status/state/commit-review/<sha>.md` at
  commit time — what the diff would expose, what was held back, what was judged safe. The
  screen shows it beside the commit. A commit with no recorded reading says so plainly rather
  than looking approved.
- **The nightly review**, one block per night: the scan's counts by severity and every
  finding with its file and line, then the fix report — what was fixed, which verification
  ran, which commit carries it, and what was deliberately left open with the reason.
- **The standing Low list.** Low findings are reported and never fixed, so they accumulate
  across nights and nobody sees the pile grow. Here they are one deduplicated list, oldest
  first, with the night each was first raised — the honest backlog of known-but-ignored.
- **Push state**: how many commits are ahead of origin, what features they carry, and the
  morning approval — the same summary that goes to Telegram, kept where it can be re-read.
- **The change log** in full: `changelog/*.jsonl` with a search and a filter by kind, since
  Pulse only shows the last twenty. Append-only, so there is nothing to edit here.

## Design

**Visual language.** The same one the assistant speaks in: dark, quiet, dense.
Charcoal background, one amber accent for anything that needs attention, a blue-grey for
links. No cards with shadows, no rounded corporate boxes — thin rules between rows, a
monospace face for ids, times, and anything the user might copy. Density over
whitespace: this is an instrument panel, not a landing page.

**Status colour is earned, not decorative.** Grey is normal, amber is `warn`, red is
`alert`, and nothing else is coloured. If every row is coloured, the board stops working
— the same reason the watcher stays silent by default.

**Layout.** A fixed left rail with the ten screens, content in a single column capped
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

## Phases

Ten screens is not one sitting. The order below is chosen so that **every phase ships
something usable on its own**, and so that the risky part — writing to the files the whole
system reads — comes last, after the panel has proved it can read them correctly.

Each phase becomes its own task with its own spec and tests when it is started; `t1037` is
the umbrella. The hour figures are estimates with no measured basis — nothing comparable has
been built here, and `store.py similar` has nothing to compare against — so treat them as
the order of magnitude, not a promise.

**Phase 1 — the shell, and Pulse.** (~3 h)
One `panel/` package: `server.py` on `127.0.0.1:8091`, the left rail, one CSS file, the
systemd unit. Then the Pulse screen, read-only: probes with their age against TTL, timers
with next and last run, the queues, the last twenty change-log lines, refreshing itself.
*Ships:* the answer to "is it alive and did anything happen" without an SSH session.
*Risk:* none — nothing is written.

**Phase 2 — Changes and review.** (~3 h)
Screen 10. Commits with their task id, the spec and tests behind each, the nightly scan and
fix reports, the standing Low list, push state, the full change log with search. Needs one
addition outside the panel: the commit-time security reading has to start being written to
`status/state/commit-review/<sha>.md`, or there is nothing to show.
*Ships:* the development record he asked for, and it is all read-only git and files.
*Risk:* none.

**Phase 3 — Zirka.** (~4 h)
Screen 4: today's reading against its budgets, the pipeline stage by stage, the computed
facts, calibration beside the feedback, the reference list — and the **paste textarea**,
which is the first write and the one that solves a problem that exists today. Then the
action buttons, which are subprocess calls to scripts that already exist.
*Ships:* a way to feed a long reference in and re-read the day without Telegram or a
terminal.
*Risk:* low — writes go through `astro_learn.py` and `mood.py`, not by hand.

**Phase 4 — Bruno.** (~3 h)
Screen 5: what was sent, what the dedup dropped and why, the archive with its real span and
the search, topics with *Collect now*, the chat and its dropped log, the prompts, the voice.
*Ships:* the first look inside the news dedup, which is the piece most likely to be wrong.
*Risk:* low.

**Phase 5 — Prompt and Scenarios.** (~4 h)
Screens 2 and 3: the assembled system prompt with the facts that did not fit, `persona.md`
and `CLAUDE.md` in an editor with a diff and the restart banner, the scenario prompts with
run and dry-run.
*Ships:* the thing that justified the project — showing the assistant to itself.
*Risk:* real for the first time. These files change the running session, so: explicit save,
a diff before it, and the banner saying a restart is needed.

**Phase 6 — Tasks.** (~3 h)
Screen 9: the four columns, drag to change a date, close, request a block. Writes go through
`store.py`, so the append-only log stays the only store.
*Ships:* the board for what is currently a list in a chat message.
*Risk:* low, bounded by `store.py`'s own validation.

**Phase 7 — Memory and Sources.** (~4 h)
Screens 6 and 7: facts with their two limits, the archive with reindex and search; the 603
channels with search, disable, priority and *Remove dead*; the mail and social filters with
*Test on the last 24 h*.
*Ships:* the lists that are painful precisely because they are lists.
*Risk:* moderate — the channel list lives in `config.local.json`, so every write is atomic
(t1043) and the file is backed up before a bulk action.

**Phase 8 — Rules.** (~3 h)
Screen 8: configuration as a form with defaults and overrides visible, permissions as
switches, the timer schedule, the read-only key list.
*Ships:* the last screen, and the one that makes the panel authoritative.
*Risk:* the highest in the project — a bad write here breaks every probe and timer at once.
It goes last on purpose: by then the panel has been reading these files for weeks, and the
atomic-write path is proven.

**Not a phase:** authentication, remote access, mobile beyond Pulse. If the panel ever needs
to be reachable from outside this machine, that is a version of its own.

## Out of scope

- Chat with the assistant: Telegram and the terminal already do it.
- Secret values in any form.
- Remote access, accounts, roles.
- Charts and analytics beyond token spend per day; a graph is not an answer.
- Editing the change log or the task log by hand — both are append-only by design.
