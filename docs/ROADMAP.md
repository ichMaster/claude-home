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
`failed` state is rendered as failed; the assembled prompt equals what `start.sh` builds,
checked by reading `start.sh` itself rather than by restating its order (t1115).

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

### v5.4 Rules (reading, done 2026-11-01)

**Goal:** make visible what governs the assistant.

**Description.** Configuration as a table rather than JSON: every key with its default,
the effective value, and whether `config.local.json` overrode it — with the personal
values masked, because the panel listens on the local network. Permissions
as they actually are, which turned out to be no allow/deny list anywhere plus prose in
`CLAUDE.md`, each rule shown beside the file it stands on. All 14 systemd timers with
their schedules or intervals, what they run, and a journal tail. Which `.env` files exist,
and the names of the variables inside them — never a value.

**Narrowed by the owner (2026-11-01):** the reading shipped first and wrote nothing. Turning
the prose into switches moved to **v5.8**, because a switch that cannot tell who flipped it is
decoration — and the machine-readable permissions it needed were built there too. The
settings form arrived with v5.8; this version is the reading half.

**DoD (met):** the merged configuration, the real permissions, the schedule and the key
list are all answerable in the browser without a terminal; no masked value and no key
value reaches the HTML.

**Tests:** 52 in `tests/test_panel_rules.py` — masking by key prefix, a list rendered as a
count, the schedule against real `systemctl show` output, a key file's names without its
values, every standing rule's source re-read, and `?unit=` refused for anything systemd did
not name.

### v5.5 Tasks board (done 2026-10-31)

**Goal:** the one view chat is bad at.

**Description.** Backlog / today / period / closed as columns, with drag to change a
date, a checkbox to close, and the 📌 flag for a time block. The calendar stays the
source of truth for events; the board shows them and can unlink.

**DoD (met):** closing a task on the board renames its all-day event `☐ → ☑` in the
calendar. Drag was refused — it needs a frontend framework this design forbids — so a date
changes through the «на вихідні» / «на тиждень» buttons instead.

### v5.6 Sent (done 2026-11-01)

**Goal:** know what the system actually said.

**Description.** `notify.sh` appends every outgoing message to
`status/state/chat-log.jsonl` — when, which bot, what kind, delivered or not, whether voice
went with it — and the panel reads that log, newest first, metadata by default. This
replaces the chat screen asked for on 2026-10-31 and dropped on 2026-11-01: the owner
listens rather than reads, so a send box in the panel would duplicate a worse channel and
be the only outward write on an unauthenticated port.

**DoD (met):** "did the 20:03 digest say anything, or did it run and stay silent" is
answerable without a phone — and a message Telegram refused is visible as refused, which is
the half that justifies keeping a log at all.

**Tests:** 21 in `tests/test_sent.py` — the record's shape, `ok` following Telegram's codes
rather than an assumption, the kind falling back to the calling script (and ignoring a /tmp
wrapper), the trim keeping the line just written, a torn line skipped, the filters, the
counters, and the body hidden unless `panel.sent_bodies` is on.

### v5.7 Authentication (done 2026-11-01)

**Goal:** the panel knows who is asking.

**Description.** One shared password — one machine, one person, so no accounts and no roles.
`hashlib.scrypt` with a random salt, stored in `.env.panel` (mode 600, git-ignored) and set
from a terminal prompt by `panel/auth.py set`; a session token of 32 random bytes held in
memory with a 12-hour expiry, in an `HttpOnly`, `SameSite=Strict` cookie; failed attempts
counted per source address, locked after five, every attempt appended to
`status/state/panel-auth.jsonl`. `panel.host` returns to `tailscale` at the same time, so the
listener is on his own devices and the traffic between them is WireGuard-encrypted — that
half costs one setting and removes the whole class of "someone else on the Wi-Fi". No
password file means the panel serves only the login page with the instruction for setting
one: it fails closed, never open.

**Why it stopped being refused.** It was in «deliberately not doing» until v5.4 was built and
its review found the journal pane publishing the owner's calendar to the network, and until
v5.8 turned out to be blocked by a decision that belonged to no version at all (2026-11-01).

**DoD (met):** a wrong password is refused and logged, a right one lasts twelve hours, an
expired token is refused, and `panel/auth.py clear` is a terminal escape hatch out of a
lockout. `panel.host` deliberately stayed `0.0.0.0`: the tailnet holds this machine and the
owner's phone, and the machine he works from is not on it — narrowing would have locked him
out, which was this version's real risk.

**Tests:** 54 in `tests/test_panel_auth.py` — the password cases and a malformed record, the
lock (including the concurrent burst that used to slip past it), the log that cannot be grown
without bound, a negative `Content-Length`, clearing the password closing live sessions, and
the gate end to end over a real socket.

### v5.8 Editing (done 2026-11-01)

**Goal:** change the rules from the panel, not only read them.

**Description.** Configuration as a form, permissions as switches that genuinely bind,
timer times that rewrite the unit and reload systemd, and the editors for `persona.md` and
`CLAUDE.md` from v5.1.

**Shipped after v5.7**, because a write needs a signature. The panel runs as `ich`, the same
user as the session and the timers, so until it could tell who was asking, every write stayed
in the terminal. Permissions and secrets still do: they are set with `tools/permissions.py
set` and `panel/auth.py set`, from a terminal, by the owner's standing rule.

**Tests (met):** a schedule change rewrites the unit and reloads systemd, and the unit is
restored automatically if it stops loading; an invalid calendar expression is rejected before
writing; the editors refuse an empty file and a halving; every write goes through the
versioned, locked path; and the form cannot touch a masked value, a permission, a list, or
the settings that protect the panel itself.

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
- **Multi-user and tenancy.** One machine, one person.
- ~~**Authentication.**~~ Refused until 2026-11-01, when it became **v5.7**: the panel was
  bound to the whole local network on 2026-10-31, v5.4's review found the journal pane
  publishing the owner's calendar across it, and editing turned out to be blocked by a
  decision that belonged to no version. Reading stayed safe by construction — personal values
  masked, journal bodies withheld, keys by name only — but writing needs a signature.
- **Secrets in any interface but the terminal.** The panel may show that a key exists,
  never what it is.
- **A chat window in the panel.** Asked for on 2026-10-31, dropped on 2026-11-01: the owner
  listens rather than reads, so the panel would duplicate a worse channel, and a send box
  would be the only outward write on an unauthenticated port. What survived is v5.6, which
  only reads what was sent.
