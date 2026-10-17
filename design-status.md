# Status, operations, schedules — the architecture proposal

## What this changes in the original sketch

The original four categories mixed two different axes:
- **where the data comes from** — local system / external service / web;
- **what the thing is** — an observation or an action.

"Operations" is not a category of statuses; it has a different nature: side effects,
permission, an audit trail. So there are three primitives, not four:

| Primitive | Essence | Property |
|---|---|---|
| **Probe** (`status/probes/*`) | returns a fact | no side effects, safe to run any time |
| **Operation** (`ops/*`) | changes state | needs permission, is written to a log |
| **Schedule** (`schedules/*`) | when, what to collect, where to send | knows nothing about the internals |

The category ("system / world / service") stays — but as a **tag in metadata**, not as
a directory tree. A tree ossifies on the first probe that is both local and
service-backed (example: the outage schedule — an external API, but about your home).

## One contract

Every probe prints a single JSON object:

```json
{"id":"loe","ok":true,"severity":"info","value":{"cherga":"4.1","off":[["18:00","22:00"]]},
 "text":"Черга 4.1: без світла 18:00–22:00","ts":"2026-10-17T18:40:00+03:00","ttl":900}
```

- `text` — a ready-made line for the digest, so the schedule does no formatting;
- `value` — machine-readable data, so today can be compared with yesterday;
- `severity` — `info | warn | alert`, decides whether to send at all;
- `ttl` — how many seconds the answer stays fresh.

## Three optimizations that actually matter

**1. A TTL cache.** Two schedules at 08:00 and 08:05 must not hit the same API twice.
This matters most for paid APIs (Deepgram, ElevenLabs) and for the outage source, which
dislikes frequent requests.

**2. Send on change, not on schedule.** The main risk here is not complexity but noise:
if every morning brings the same "disk 50%, services alive", it stops being read within
a week. So a schedule carries a condition:
`when: always | if changed | if severity>=warn`.
For the outage schedule, "if changed" is clearly the right mode: on the day this was
written the schedule was updated at 16:21, and *that* was the news, not the existence of
a schedule.

**3. Delivery levels.** `info` — a quiet text message; `warn` — text with a marker;
`alert` — text plus voice. One channel, three volumes.

## Operations kept separate

`ops/` is for things that do something: restart a container, free disk space, refresh an
index, rebuild a model. Different rules apply:
- only entries with an explicit `auto: true` flag run on a schedule;
- everything else runs on the assistant's initiative or on request, with confirmation;
- every run appends a line to `ops/log.jsonl`.

## Where to start (instead of building everything)

Four probes that already have data and proved useful on day one:

| id | tag | what it shows |
|---|---|---|
| `loe` | service, home | grid queue plus today's outage schedule, "if changed" |
| `host` | system | disk, memory, uptime, temperature |
| `services` | system, network | tmux session, systemd units, matrix-agora containers, ports |
| `weather` | service | the day's weather |

Then, as needed: air alerts, mail, calendar, news by topic.

## File layout

```
status/
  probes/loe.py        # prints JSON
  probes/host.sh
  probes/services.sh
  probes/weather.py
  meta/loe.json        # {"tags":["сервіс","дім"],"ttl":900}
  run.sh loe host      # runs, caches, returns a JSON array
  cache/
ops/
  log.jsonl
schedules/
  morning.json         # {"cron":"3 8 * * *","probes":["loe","weather"],"коли":"завжди"}
  evening-check.json   # {"cron":"33 16 * * *","probes":["loe"],"коли":"якщо змінилось"}
notify.sh              # already exists: Telegram delivery with no session involved
```

A systemd timer runs the schedule by calling `status/run.sh` and `notify.sh`. No session
is needed for that, so it survives restarts and reboots.
