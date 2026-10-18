# Vision

## What Noos is

A personal assistant that lives on one machine and stays awake. Not a chatbot that
answers when addressed and forgets, and not an automation framework that fires rules —
something in between: a session with memory, senses and a voice, that can be talked to
and that occasionally talks first.

It is built for one person. Everything it knows is about him, stays on his machine, and
is readable by him in plain files.

## Why it exists

Three problems, in order of how much they hurt:

1. **State is scattered.** Power schedule on a website, air alerts in an app, mail in
   Gmail, events in Calendar, tasks in the head, server health in `systemctl`. Checking
   all of it costs more attention than acting on it.
2. **Assistants forget.** Every new session starts from zero, so the same context is
   retyped forever. A assistant that cannot remember yesterday is a search engine with
   manners.
3. **Automation is noisy.** A cron job that reports "disk 50%, services alive" every
   morning stops being read within a week, and then the one morning it matters is missed
   too.

## Principles

**Silence is the default.** The assistant reports a change or a problem, not a
heartbeat. If nothing happened, nothing is sent. A message that arrives is therefore
worth opening.

**One source of truth per thing.** Settings live in `config.json`, facts in
`memory/facts/`, tasks in `tasks/tasks.jsonl`, the plan in the `Noos` calendar. No
component keeps a private copy; every interface — chat, terminal, future panel — edits
the same files.

**History is append-only.** The change log and the task store are never rewritten. A
correction is a new line, not an edit. What was done yesterday stays visible, including
the mistakes.

**Honest about certainty.** Verified, assumed and unknown are different words. A guess
delivered in the voice of knowledge is the one failure mode that makes an assistant
worse than nothing.

**The user's data is the user's.** Keys never leave `.env.*` files with mode 600.
Conversation archive, facts, tasks and caches stay out of the repository. Nothing is
sent to an external service that was not asked for.

**The user's calendar is sacred.** The assistant writes only to its own calendar, never
edits events it did not create, and never sends mail on the user's behalf without an
explicit instruction.

**Reversible by design.** Every automated action can be undone, and the assistant says
how. Anything that cannot be undone needs a human sentence first.

## What it is not

- Not a product. There is no multi-user story, no tenancy, no onboarding.
- Not a wrapper around one model's chat window; the model is a part, not the point.
- Not an autonomous agent that acts on its own initiative in the world. It observes
  continuously; it acts when asked, or when a rule the user wrote says so.
- Not a place for secrets to be convenient. Credentials stay inconvenient on purpose.

## How success is measured

- Messages that arrive are read, not dismissed.
- The user stops checking three apps in the morning.
- "What did we decide about X" has an answer within two seconds.
- A week of no attention leaves the system in a working state, not a broken one.
