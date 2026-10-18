# Roadmap

Status as of 2026-10-18. Items are ordered by value per hour of work, not by ambition.

## Done

- Always-on session with persona, project instructions and pinned facts
- Telegram channel: text and voice both ways, command menu, session-free delivery
- Probe framework with a uniform JSON contract and a TTL cache
- Probes: power outages, air alerts, weather, host, services, news by topic, mail,
  calendar, tasks, change log, YouTube
- Watcher that reports only changes and problems
- Digests at 08:03 and 20:03 assembled by a separate headless session
- Social check every two hours: Facebook and LinkedIn, personal items only
- YouTube digest at 18:05 over 600+ subscriptions with a rotating poll and a queue
- Conversation memory: FTS5 plus embeddings, hybrid search, incremental indexing
- Pinned facts store feeding the system prompt
- Tasks: append-only event log, Ukrainian date parsing, calendar blocks and all-day
  mirroring, task-to-event links
- Append-only change log enforced with `chattr +a`
- Configuration split into committed defaults and git-ignored local values
- Public repository with English documentation, comments and commit messages

## Next

**1. Admin panel, phase one.** Local web UI on `127.0.0.1:8091`, one file, no build
step. Three screens that pay for themselves immediately:
- the assembled system prompt as the session sees it, plus the facts that fit into it
  and the ones cut by the limit;
- the scheduled scenarios (`digest-prompt.md`, `social-prompt.md`,
  `youtube-prompt.md`) with "run now", "dry run" and the output of the last runs;
- a pulse screen: probes, timers, errors, queue sizes.
It edits the same files the session reads, and writes every change to the change log.

**2. The planner (step 2 of the task concept).** Lay out tomorrow's blocks
automatically: free slots from the calendars, outage windows from the `loe` probe
avoided, deep work in large blocks, nothing denser than four hours a day. Blocks moved
by hand are respected rather than overwritten.

**3. Evening review.** At 23:30, list the day's blocks and ask one question: what was
closed? One voice reply closes or defers them all.

**4. Mail candidates into tasks.** A letter with a deadline (ASU, GoITeens, taxes)
becomes a proposed task with a date, confirmed by a single "yes".

**5. Reaction to outage schedule changes.** When a new schedule lands on a day that
already has blocks, move them and say what moved.

## Later

- **Admin panel, phase two**: facts editor, probe registry, permissions as switches,
  channel settings, an audit of outward actions (mail sent, events created).
- **Telegram via MTProto**: a local MCP server over Telethon for contacts, dialogs and
  history — the bot API cannot provide any of them. Requires a user session file, which
  is as sensitive as the account itself.
- **Mail without the connector**: Google OAuth with a Gmail scope, so the mail probe
  works in headless runs instead of depending on the interactive session. App passwords
  are unavailable on this account (passkey-only sign-in).
- **Weekly review** on Sunday evening: what was done, what stalled, what to drop.
- **Operations (`ops/`)**: actions with side effects — restart a container, free disk
  space, rebuild the index — each requiring permission and writing to its own log.
- **Lumi (Lili) moving to this server**: test, container, deployment scripts, and voice
  for the matrix-agora agents using the existing voice stack.

## Deliberately not doing

- **Facebook and Instagram feeds or Messenger.** Meta removed the APIs; the only route
  left is an unofficial client, which violates the terms, breaks weekly and risks the
  account. Facebook stays as e-mail notifications only.
- **YouTube Data API.** The per-channel RSS feeds already answer "what is new" without
  OAuth or quotas. The API would only be worth it for automatic subscription sync.
- **Multi-user support, authentication, tenancy.** One machine, one person; the panel
  listens on localhost and is reached over SSH or Tailscale.
- **Secrets in any interface but the terminal.** Keys stay in `.env.*` with mode 600.
  The panel may show that a key exists, never what it is.
