# Admin panel — functionality and design

Status: all eleven screens built (phases 1-11), 2026-11-01. What is left is not a phase: TLS, and the decision to narrow the bind back to the tailnet.
Target: v5 of [ROADMAP.md](../ROADMAP.md).

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

Ten are built. Each section below describes what the code renders today; a promise that was
made and not kept is not listed as a feature.

### 1. Pulse (home)

The answer to "is it alive and did anything happen". A status board, no form on it, refreshing
itself every `panel.refresh_sec` seconds.

- **Probes**: id, severity dot, the one-line answer, age against the probe's own TTL. A cache
  older than its TTL renders stale rather than silently old, and an answer with no timestamp
  is stale too — unknown age is not freshness.
- **Timers**: unit, next run, last run, and how it went — «успішно», the failure with its
  exit code, or «виконується» while the run is still in flight (t1114).
- **Queues**: the YouTube pending count and its back-off while it is still in force, the
  mail state's last UID or «невідомо» when the probe has never run, and the watcher
  signatures that are currently louder than `info`.
- **Recent changes**: the last `panel.changes` lines of the change log, newest first.

### 2. Prompt

The screen that justifies the project: the assistant shown to itself.

- The **assembled system prompt**, in the order and shape `start.sh` builds it: `persona.md`,
  the pinned facts, the permission block (`tools/permissions.py prompt`), and the handoff note
  when the running session has one — including the case where the note was already consumed,
  because `start.sh` archives it as it reads it (t1111). Each part's size, the total, and a
  rough token estimate that says it is an estimate.
- A **"restart required"** banner when anything the session read at launch has changed since
  it started: `persona.md`, `CLAUDE.md`, the pinned facts, `config.json`,
  `config.local.json`. With no known start time it says the start time is unknown rather than
  claiming nothing changed.
- `persona.md` and `CLAUDE.md` with their size and whether they differ from the commit, and
  **an editor for each** (phase 10): empty refused, a halving confirmed, every save versioned.
- A line pointing at the Memory screen for the facts that did not fit.

### 3. Scenarios

The prompts that belong to no channel: the digest, the forecast's nine stages, the YouTube
picks, the social run, the bots, the nightly review, the watcher, the day's changes, the
handoff note.

- Per scenario: the timer that fires it with its schedule and last result, the command, and
  each prompt file with its size — a missing prompt file is named, not skipped.
- **Run**, and **dry run** where the script has one. A long run is detached through
  `systemd-run`, so the request returns at once and the run survives a panel restart.
- The scenario list is `panel.scenarios` in config, not a hardcoded table.

### 4. Zirka — the horoscope

- **Дії**: recompute the day, ask the evening question, calibrate against the day's feedback.
- **Читання проти лімітів**: today's four blocks with their character budgets.
- **Конвеєр**: the run's stages as the log recorded them.
- **Пораховані факти**: the transits with their windows, from `astro.py` — arithmetic, no
  model.
- **Правила**: the two sets kept apart — what his own days taught, and what the reference
  astrologer's readings taught.
- **Відгуки про дні**, and **Еталони**: the references with a paste box that feeds
  `astro_learn.py`, and the inbox of parked ones.

### 5. Bruno — news and video

Read-only.

- **Що відкинуто як повтор**: the dedup's decisions, which is the piece most likely to be
  wrong.
- **Що надіслано**: the news and the videos that went out.
- **Архів підписок** with its real span and a search over it.
- **Його чат**: the last turns in Bruno's own chat, and what was dropped as not the owner's.
- **Теми** and **Промпти**: the topics and the prompt files behind them.

### 6. Memory

- **Факти**: the facts that reach the prompt, with the two limits spelled out, and a box to
  add one. A fact longer than `memory.max_fact_chars` is marked with how much of it actually
  reaches the prompt (t1114).
- **Не влізли в підказку**: the pinned facts that are stored and silent — the single most
  surprising piece of state in the system, and the reason this screen exists.
- **Не закріплені**, and the pin buttons, which walk the prompt's own ranking (0→2→1).
- **Архів розмов**: the index's size and a full-text search over it. Not the hybrid search
  `memory/search.sh` runs — the embedding model is 240 MB and a page cannot wait for it; the
  screen says so.
- The page states that it shows personal material and that the login is why it may.

### 7. Sources

- **Канали**: the 603 subscriptions with the date of each one's last video from the archive,
  a search, a sort by activity or name, and per-channel *off* / *priority*. Writes go to
  `config.local.json` through the versioned, locked path.
- **Фільтри**: the mail and social lists, with a box that says how a given sender and
  subject would be classified.
- **Теми новин**: the topics and their queries.

### 8. Rules

- **Налаштування**: every setting as a dotted key with its default, the effective value, and
  whether `config.local.json` overrode it — the merge `noosconf` performs, so it is what the
  probes obey. Scalars are **editable**; values are masked for `panel.rules_masked`, and
  masked values, lists, blocks, permissions and the settings that protect the panel itself
  are refused (t1102, t1112).
- **Дозволи**: the session's permission mode, the fact that no allow/deny list is configured
  anywhere, the bot limits, the machine-readable levels the system prompt carries, and the
  standing prose rules with the file each stands on. No switches: permissions are set from a
  terminal.
- **Розклад**: all fourteen timers — the command, every `OnCalendar` line or the interval for
  those that have none, catch-up, next, last, the result — with the `OnCalendar` lines
  **editable** (validated by systemd, rolled back if the unit stops loading) and a journal
  tail per unit showing systemd's own lines only.
- **Ключі**: which `.env` files exist, their permissions, and the names of the variables
  inside them. Never a value.

### 9. Tasks

Backlog / today / period / closed as four columns. Buttons, not drag — drag needs a frontend
framework this design forbids (t1074): close, start and stop the clock, defer to a date or a
period, request a time block. Events are shown under their task with their calendar time.
The calendar remains the source of truth for events; the board never invents one, and does
not delete one.

### 10. Changes — what was built and how it was reviewed

- **Пуш**: how many commits are ahead of the public remote, or that the answer is unknown.
- **Коміти**, newest first: hash, date, subject, the task id parsed out of it, whether it is
  still local, its spec, the tests naming its task, and **the commit-time security reading**
  from `status/state/commit-review/` under either spelling of the sha (t1110). A commit with
  no reading says «не записано»; a commit with no task id is flagged.
- **Нічні ревʼю**: one block per review, with the counts its own verdict states, or
  «не розібрано» when the report is in a shape the parser does not know.
- **Накопичені Low**: the Lows that were raised and not fixed, oldest first, with the night
  each was first seen — a Low named in a fix report is not listed.
- **Журнал змін** in full, with a search over weeks rather than over the display window.

### 11. Sent

Reworked on the owner's request (2026-11-01), replacing the chat screen the same owner had
asked for a day earlier. The reasoning that killed it is his own usage: **he listens, he does
not read.** A send box on the panel duplicates a channel that already works better — Telegram
with voice — and it would be the only screen that writes *outward*. Its single genuine advantage, asking about what is on screen without losing
the context, is worth one line of context and not a second conversation.

What is left is the half that has value on its own: **nothing in this system records what it
actually said.** The digest, the forecast, the reminders and the probe reports go out through
`notify.sh` and are gone. "Did the 20:03 digest say anything, or did it run and stay silent"
is unanswerable today except by scrolling a phone.

- **`notify.sh` appends one line per outgoing message** to `status/state/chat-log.jsonl`:
  when, which bot, what kind (probe, digest, forecast, reminder, restart, answer), the
  delivery result — Telegram's own HTTP code, not an assumption — and whether voice went
  with it. The **kind** is the calling script's own name when no `--kind` is given, read from
  the parent process, so a digest says `digest-headless.sh` and a reminder says `remind.py`
  without a single caller being changed; a throwaway wrapper in `/tmp` is not recorded as a
  sender. The chat id is deliberately not stored: the bot's name says where it went. Trimmed
  to the newest `sent.max_lines` on append — a record, not an archive.
- **The screen reads that log**, newest first, with a filter by bot and by kind, and shows
  **metadata by default — not the body.** This is deliberate and it is the lesson of t1094:
  the text of a digest *is* the owner's calendar and mail. The body is shown only when
  `panel.sent_bodies` is on — the login exists now (phase 11), but a page of digests is a
  larger disclosure than a settings table, so it stays an explicit decision.
- **It answers one question the rest of the panel cannot**: a timer that ran successfully and
  said nothing looks identical to a timer that worked, in `systemctl` and in the journal
  alike. Here the silence is visible.

Nothing on this screen writes anything, outward or otherwise.

## Design

**Visual language.** The same one the assistant speaks in: dark, quiet, dense.
Charcoal background, one amber accent for anything that needs attention, a blue-grey for
links. No cards with shadows, no rounded corporate boxes — thin rules between rows, a
monospace face for ids, times, and anything the user might copy. Density over
whitespace: this is an instrument panel, not a landing page.

**Status colour is earned, not decorative.** Grey is normal, amber is `warn`, red is
`alert`, and nothing else is coloured. If every row is coloured, the board stops working
— the same reason the watcher stays silent by default.

**Layout.** A fixed left rail with the eleven screens, content in a single column capped
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
- Listens on port 8091 (8090 belongs to the matrix-agora panel). `panel.host` decides who
  can reach it: `127.0.0.1` (an SSH tunnel only), `tailscale` (the owner's own devices,
  resolved at start so a changed tailnet address cannot stop the unit booting), or
  `0.0.0.0` (every device on the local network). It runs on `0.0.0.0` since 2026-10-31 —
  the owner works from another machine on the same Wi-Fi, and loopback made the panel
  unreachable for the only person it is for. **A login since 2026-11-01** (phase 11): one
  shared password, scrypt-hashed into `.env.panel`, set from a terminal; a session token in
  the process for twelve hours; five attempts per address then a five-minute lock. There is
  no TLS — on a tailnet address the traffic is encrypted between devices, and
  `tailscale cert` is the upgrade if that stops being enough.
- The network boundary is enforced, not only declared: every request's `Host` must be an
  IP literal, `localhost`, a `*.ts.net` name or an entry in `panel.hosts` — a DNS name an
  attacker controls is refused with 403, which is what stops DNS rebinding from making an
  internet page same-origin with the panel and replaying the form token (t1069).
- **`ufw` must be told about the port.** The firewall is enabled on this machine and drops
  inbound 8091 silently — *timed out*, not *refused*, which is why it reads as the panel
  being broken rather than blocked. The agora panel on 8090 is reachable only because
  Docker publishes it and Docker writes its rules past ufw; a plain Python process gets no
  such help. Every port this project opens needs an explicit `sudo ufw allow <port>/tcp`
  (t1058).
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

**Phase 1 — the shell, and Pulse.** (~3 h) — **done 2026-10-31**
One `panel/` package: `server.py` on `127.0.0.1:8091`, the left rail, one CSS file, the
systemd unit. Then the Pulse screen, read-only: probes with their age against TTL, timers
with next and last run, the queues, the last twenty change-log lines, refreshing itself.
*Ships:* the answer to "is it alive and did anything happen" without an SSH session.
*Risk:* none — nothing is written.

**Phase 2 — Changes and review.** (~3 h) — **done 2026-10-31**
Screen 10. Commits with their task id, the spec and tests behind each, the nightly scan and
fix reports, the standing Low list, push state, the full change log with search. Needs one
addition outside the panel: the commit-time security reading has to start being written to
`status/state/commit-review/<sha>.md`, or there is nothing to show.
*Ships:* the development record he asked for, and it is all read-only git and files.
*Risk:* none.

**Phase 3 — Zirka.** (~4 h) — **done 2026-10-31**
Screen 4: today's reading against its budgets, the pipeline stage by stage, the computed
facts, calibration beside the feedback, the reference list — and the **paste textarea**,
which is the first write and the one that solves a problem that exists today. Then the
action buttons, which are subprocess calls to scripts that already exist.
*Ships:* a way to feed a long reference in and re-read the day without Telegram or a
terminal.
*Risk:* low — writes go through `astro_learn.py` and `mood.py`, not by hand.

**Phase 4 — Bruno.** (~3 h) — **done 2026-10-31**
Screen 5: what was sent, what the dedup dropped and why, the archive with its real span and
the search, topics with *Collect now*, the chat and its dropped log, the prompts, the voice.
*Ships:* the first look inside the news dedup, which is the piece most likely to be wrong.
*Risk:* low.

**Phase 5 — Prompt and Scenarios.** (~4 h) — **done 2026-11-01**
Screens 2 and 3, reading. The assembled system prompt exactly as `start.sh` builds it —
`persona.md`, then the facts block, then the handoff note while one is pending — with each
part's size and a rough token estimate. **A restart banner** when a file the session read at
launch has changed since it started, because an edit to `persona.md` is saved long before it
is in force; the session's start time comes from its own systemd unit, so nothing new is
recorded anywhere. `persona.md` and `CLAUDE.md` read-only, each saying whether it has
uncommitted changes. Screen 3 lists the scenarios from `panel.scenarios` — prompt files with
their sizes, the timer that fires them, its schedule and last result — with *run* and, where
the script has one, *dry run*; a long run is detached through `systemd-run`.
*Ships:* the thing that justified the project — showing the assistant to itself, and saying
plainly when what it was told is out of date.
*Why it came after phase 11:* this screen shows the prompt in full, pinned personal facts
included. Before the login that would have published them to the network; the editors stay in
phase 10 for the same reason.

**Phase 6 — Tasks.** (~3 h) — **done 2026-10-31**
Screen 9: the four columns, drag to change a date, close, request a block. Writes go through
`store.py`, so the append-only log stays the only store.
*Ships:* the board for what is currently a list in a chat message.
*Risk:* low, bounded by `store.py`'s own validation.

**Phase 7 — Memory and Sources.** (~4 h) — **done 2026-10-31**
Screens 6 and 7: facts with their two limits, the archive with reindex and search; the 603
channels with search, disable, priority and *Remove dead*; the mail and social filters with
*Test on the last 24 h*.
*Ships:* the lists that are painful precisely because they are lists.
*Risk:* moderate — the channel list lives in `config.local.json`, so every write is atomic
(t1043) and the file is backed up before a bulk action.

**Phase 8 — Rules, reading.** (~3 h) — **done 2026-11-01**
Screen 8 as described above: the merged configuration with overrides and masked values, the
permissions as they actually are, all 14 timers with their journals, the key list. No form,
no write path.
*Ships:* the answer to "what governs this thing", without a terminal.
*Risk:* low by construction — the only thing it can do is show. The two real risks are
disclosure, not corruption, and both are tested: a personal value out of
`config.local.json` and anything out of an `.env` file beyond a variable name.

**Phase 9 — Sent.** (~2 h) — **done 2026-11-01**
Screen 11: the log of what the system actually said. First `notify.sh` learns to append every
outgoing message to `status/state/chat-log.jsonl` — that is most of the work and it is useful
with no screen at all — then the screen reads it: newest first, filtered by bot and kind,
metadata by default, the body only behind `panel.sent_bodies`.
*Ships:* the answer to "did it say anything", which neither `systemctl` nor the journal can
give, because a timer that ran and stayed silent looks exactly like one that worked.
*Risk:* low — one more reader of one more append-only file. The thing to get right is the one
phase 8 got wrong once: the body of a message is personal content.
*Dropped from this phase:* the send box — see screen 11.

**Phase 10 — Editing.** (~4 h) — **done 2026-11-01**
The writing half of screen 8 and the editors of screens 2 and 3.

*Done (t1102):* configuration as a form. Every scalar setting is editable and the write goes
to `config.local.json` through the versioned atomic path, so a wrong value is one
`tools/versions.py restore` away. *Повернути типове* removes the override rather than writing
the default, so the committed file stays the authority. Refused by design, each for its own
reason: masked values (personal — terminal only), lists and blocks (the channels have their
own screen; a textarea of JSON is a way to corrupt a file), unknown keys (a form must not be
able to invent a setting), and permissions.

*Done (t1102):* **permissions that bind.** Phase 8 found that nothing machine-readable
governed the assistant at all. Now `config.json` carries a `permissions` block —
`free` / `ask` / `never` per named decision, plus three hard rules that are not switches —
`tools/permissions.py prompt` renders it, and `start.sh` appends it to the system prompt
beside the persona and the facts. That is what makes a change bind: the session is told, and
the restart banner says when it is not in force yet. **They are set from the terminal**
(`tools/permissions.py set`), not from the panel, because that is the owner's standing rule
and a password on a LAN page is not a shell on the machine. The screen shows the levels and
offers no switch.

*Done (t1103):* **the editors and the timer times** — the two most destructive writes in the
project, so each guard answers a way the panel could destroy rather than change.
`persona.md` and `CLAUDE.md` are editable by name from a fixed list, never by a path from a
form; an empty save is refused; a save that halves the file is refused until the same press
repeats with the confirmation box, because a truncated paste looks exactly like an edit; the
write is versioned, and both files joined `versions.files` along with the systemd unit
directory, which is in no repository at all. A timer's `OnCalendar` lines are editable with
systemd's own parser validating every spec **before** anything is written, the unit versioned,
then `daemon-reload` — and if the unit stops loading, the previous content is restored and
reloaded automatically. A panel that can break a timer must be able to put it back without a
human, because the symptom of a broken timer is silence. Interval timers are shown and not
editable: rewriting a different directive is a separate decision.

*The panel is now complete* — eleven screens, eleven phases, with phase 9 (Sent) the only one
outstanding.

**Phase 11 — Authentication.** (~4 h) — **done 2026-11-01**
Added on the owner's request, 2026-11-01. It was in "not a phase" until phase 8 showed what
an open port means in practice, and until phase 10 turned out to be blocked by a decision
that belonged to no phase at all: editing cannot ship without it, so it is a phase.

*The design, in the order the requests hit it:*

- **Narrow the bind back to the tailnet.** `panel.host` returns to `tailscale`, so the
  listener is on his own devices rather than on every device on the home Wi-Fi, and the
  traffic between them is WireGuard-encrypted. This is the half that does the most work for
  the least code — it is already implemented (`resolve_host`), it is one setting, and it
  removes the entire class of "someone else on the network".
- **One shared password, stored as a hash.** No accounts, no roles: one person, one secret.
  `hashlib.scrypt` with a random salt — stdlib, no dependency — written to `.env.panel`
  (mode 600, git-ignored) by `panel/auth.py set`, which reads the password from a terminal
  prompt and never echoes or logs it. The panel reads the hash at start; a missing file means
  no password is set, and then the panel serves **nothing but** `/login` with the one-line
  instruction for setting it, rather than falling open.
- **A session cookie, in memory only.** `/login` takes the password, compares with
  `hmac.compare_digest`, and on success mints 32 random bytes as a token held in a dict in
  the process with an expiry (`panel.auth.ttl_hours`, 12). The cookie is `HttpOnly`,
  `SameSite=Strict`, `Path=/`. Memory-only is deliberate: a restart logs everyone out, and
  the panel gains no second on-disk secret to protect.
- **Rate limiting, because a LAN password without it is a dictionary away.** Failed attempts
  are counted per source address (`panel.auth.max_attempts`, 5) and the address is locked for
  `panel.auth.lock_min` (5), every attempt appended to `status/state/panel-auth.jsonl`. The
  log is the point as much as the lock: an attempt from an address that is not his is
  something he should be able to see.
- **The form token stays.** It solves a different problem — a page on another origin driving
  this one (t1069, t1085) — and a login does not replace it.
- **No TLS, stated plainly.** Plain HTTP on a tailnet address is encrypted by WireGuard
  between the devices and in clear only on each device itself. If that stops being enough,
  the upgrade is `tailscale cert` plus `http.server` with TLS: a real certificate for the
  `*.ts.net` name with no private CA to run. Not in this phase.

*Ships:* the panel knows who is asking, which is what phases 9 and 10 are waiting on — the
message bodies on the Sent screen and every form in Editing.
*Risk:* moderate and of an unusual kind — the failure mode is not a leak but a lockout:
getting the password check wrong, or the cookie path wrong, locks him out of his own panel.
So the first thing this phase gets is a test that a wrong password is refused, a right one
accepted, and an expired token refused, and the second is a terminal escape hatch
(`panel/auth.py clear`, which drops the password file and the sessions).

**Not a phase:** remote access from outside the tailnet, accounts and roles, mobile beyond
Pulse. Authentication left this list on 2026-11-01 and became phase 11, because phase 10
cannot exist without it.

## Out of scope

- A chat window, and with it any outward write. Screen 11 reads what was sent and offers no
  way to send (2026-11-01). Telegram with voice is the channel; the panel is the instrument
  panel beside it.
- Secret values in any form.
- Remote access, accounts, roles.
- Charts and analytics beyond token spend per day; a graph is not an answer.
- Editing the change log or the task log by hand — both are append-only by design.
