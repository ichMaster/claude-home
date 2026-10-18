# Mission — Noos

## In one sentence

Noos is an always-on assistant that lives on one machine, keeps a durable memory of its
owner, watches the few things that actually matter, and speaks only when there is
something to say — growing from a terminal session into a system with its own senses,
schedule, and control panel.

## What we are building

A deliberately small project where the **mind comes first and the interface later**. The
mind is a long-running Claude Code session with a persona, pinned facts, and a
searchable archive of every conversation. The senses are probes: tiny scripts with one
JSON contract, so a new source of truth costs twenty lines, not a subsystem. The hands
are a calendar, a task log, and a voice.

Everything the assistant knows lives in plain files on that machine: facts in
`memory/facts/`, tasks in `tasks/tasks.jsonl`, settings in `config.json`, history in
`changelog/`. Interfaces — Telegram, terminal, and from v5 an admin panel — are clients
of those files, never owners of a private copy.

## For whom

A private assistant for one person. There is no tenancy, no sign-up, no second user.
What is built for an audience of one can be blunt: it may interrupt at 03:00 if the
power schedule changed, and it may stay silent for a day if nothing did.

## Principles

**Silence is the default.** The assistant reports a change or a problem, never a
heartbeat. A message that arrives is therefore worth opening.

**Simplicity first.** Complexity arrives by version, not all at once. A probe is a
script that prints JSON; a scheduler is a systemd timer; the store is an append-only
file. Nothing is introduced until the simple version has visibly failed.

**One source of truth per thing.** Settings, facts, tasks, and the plan each live in
exactly one place. Every interface edits those same files.

**History is append-only.** The change log and the task store are never rewritten; a
correction is a new line. Yesterday stays visible, mistakes included.

**Honest about certainty.** Verified, assumed, and unknown are three different words. A
guess delivered in the voice of knowledge is the one failure that makes an assistant
worse than nothing.

**The owner's data is the owner's.** Keys stay in `.env.*` with mode 600 and never reach
any interface but the terminal. The conversation archive, facts, tasks, and caches stay
out of the repository.

**The owner's calendar is sacred.** The assistant writes only to its own calendar,
never edits an event it did not create, and never sends mail on the owner's behalf
without an explicit instruction.

**Reversible by design.** Every automated action can be undone and the assistant says
how. Anything irreversible needs a human sentence first.

## Non-goals

- Not a product: no multi-user story, no onboarding, no settings that exist "for
  completeness".
- Not an autonomous agent acting in the world on its own initiative. It observes
  continuously; it acts when asked or when a rule the owner wrote says so.
- Not a wrapper around a chat window: the model is one component among several.
- Not a second place for secrets to live conveniently. Credentials stay inconvenient on
  purpose.
- Not a general automation framework. Anything with side effects is an **operation**
  (v6), kept deliberately separate from the probes.

## Glossary

**Session** — the long-running Claude Code process with the assembled system prompt;
the mind.

**Probe** — a script under `status/probes/` that prints one JSON object and has no side
effects. Safe to run at any moment.

**Operation** (from v6) — an action that changes something outside the assistant:
restart a container, free disk space. Requires permission and writes its own log.

**Scenario** — a prompt executed by a headless session on a timer: the digest, the
social check, the YouTube digest. Editable text, not code.

**Facts** — short pinned statements about the owner, injected into the system prompt at
start. Hand-curated, roughly twenty of them.

**Archive** — every transcript indexed into SQLite with full-text and vector search; the
long memory the session consults on demand.

**Task** — work to do. **Event** — a slice of time booked for a task in the `Noos`
calendar. One task may own several events.

**Panel** (from v5) — a local web interface for inspecting and editing the same files
the session reads: prompt, facts, scenarios, schedule, permissions.
