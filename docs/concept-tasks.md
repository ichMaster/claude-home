# Tasks and planning — the concept

Date: 2026-10-17. Status: proposal; step 1 is built, step 2 is not.

## Principle

Tasks live in a plain local file; the plan lives in a **separate** calendar. The user's
real events are never touched: Noos only creates and removes its own blocks in the
`Noos` calendar. Every trace it leaves can be removed with one "clear the plan".

## 1. Where tasks come from

| Source | What it looks like |
|---|---|
| Telegram, text | `+ fix the indexer by Friday` — everything after `+` becomes a task |
| Telegram, voice | "add a task: call the bank tomorrow" — recognized and created |
| Menu command | `/task` lists, `/plan` reschedules the day |
| Mail | the digest proposes candidates: "ASU I-20 — action required" → add? yes/no |
| Noos itself | when the user says "remind me", "don't let me forget", it asks whether to file it |

Dates and times are parsed from natural language: "завтра", "у п'ятницю",
"до 1 листопада", "щовівторка". Without a date a task simply sits in the backlog.

## 2. Where they live

`tasks/tasks.jsonl` — one line per event, append-only (like `changelog/`): creation,
change, closing. Current state is replayed from the history, so nothing is lost and it
stays visible when and why a task appeared.

Fields: `id`, `title`, `project`, `due`, `estimate` (minutes), `priority`, `energy`
(deep work / routine), `status`, `source`, `created`, `closed`.

`tasks/open.md` — a derived human-readable view, for glancing at or opening in an editor.

## 3. Planning in the calendar

A separate **`Noos`** calendar, created once in Google Calendar (only its id is needed).
Time blocks go there.

How slots are chosen:
1. Busy time is read from the user's calendars (personal, family) — those hours are
   off limits.
2. Power-outage windows from the `loe` probe are excluded — heavy work is not scheduled
   into a blackout; offline routine goes there instead, or nothing.
3. Tasks are laid out: deep work in large blocks, routine in small ones.
4. Night hours count as working hours, because that is when the user often works.
5. Nothing denser than 3-4 hours of substantive work per day.

Each block is an ordinary event named after the task, with its id in the description.
A block moved by hand is respected at the next planning pass, not overwritten.

## 4. Rhythm

- **08:03, morning digest** — adds a "Plan for the day" section: 3-5 blocks, the nearest
  deadlines, what is overdue.
- **20:03 or 23:30** — a short "what did you close?": the day's blocks are listed, the
  user answers in one voice message, Noos closes or defers them.
- **Any time** — `/tasks`, `/plan`, `+ new task`, "done: indexing".

## 5. Boundaries

- Writes only to its own calendar. The user's events are read-only, even when a conflict
  is visible.
- Sends nothing to anyone on the user's behalf without an explicit instruction.
- No "have you done it yet?" more than once a day.
- The task file is append-only: history is never rewritten.

## 6. Steps

**Step 1 (built):** the `tasks.jsonl` store, the date parser, `/tasks`, `+task`,
`done: …`, and a "Tasks" section in the digest. No calendar involved.

**Step 2 (not built):** the `Noos` calendar and automatic planning that accounts for
busy time and the outage schedule; tomorrow's blocks are laid out in the evening.

**Step 3:** candidates from mail (a letter with a deadline → a proposed task) and a
Sunday review: done, stalled, drop.

## 7. What is needed from the user

1. Storage: local (recommended) or Notion — the connector exists, but it is slower and
   network-dependent. **Decided: local.**
2. Create an empty `Noos` calendar and name it — Noos finds the id itself. **Done.**
3. Working boundaries: when not to plan anything, and how many hours of substantive work
   count as a day's worth. **Decided: any time except sleep 00:00-08:00.**
