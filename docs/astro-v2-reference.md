# The astro forecast, v2 — learning one astrologer's method in three phases

What this is: the plan for replacing the morning astrology reading (v1, recorded as-is in
`docs/astro-v1-asis.md`) with one built on the method of a working astrologer the owner
trusts. Not his sentences — his way of getting from a sky to a meaning.

The owner set the shape on 2026-11-11: «спочатку навчитись інтерпретувати вже готовий
прогноз від [астролога] який я буду надавати сам кожного тижні, а потім навчитись робити
пояснення як він фактів, а потім вибирати самі факти. Тобто 3 кроки і мета скопіювати [його]
підхід.» (the name is elided here on his instruction, 2026-11-11 — see *The one policy
change*.)

So the capability is taken apart into the three things it is actually made of, and each one
is learned against a reference that already exists:

1. **Read his finished calendar** — translate, slice it into days, pick what is loud, say it
   for the ear. No astrology of our own. The sky comes from him.
2. **Explain the same facts ourselves** — he supplies the facts, we supply the meaning, and
   his meaning is the answer sheet. The asset built here is a vocabulary: factor → meaning.
3. **Choose the facts ourselves** — our own ephemeris, his ranking. The answer sheet is
   which factors he names for a day and how loudly.

Each phase is useful on its own: phase 1 already gives a listenable daily reading, so there
is no long stretch of work with nothing to show for it.

## Why this, and not another rewrite

v1 has been rewritten three times — atmosphere, then event prediction, then checkable states
— and each time the shape was argued from first principles and then found not to work. Both
earlier attempts failed on **meaning**, not form: the figures were right (three of four
factors matched a real reference to the degree, 2026-10-31) and the readings still said
nothing he recognised.

What this astrologer has that we do not is exactly that: a reliable route from a computed
factor to a meaning in a life. He publishes it daily, for this chart, with the formula
printed beside every claim. That is a ready-made answer sheet, and the three phases are three
ways of marking our work against it.

## What his product is

A personalised hourly Moon calendar, in Russian, computed for the owner's own chart. One day
of it is a sequence of timed entries. Anatomy, with every value replaced by a
placeholder — neither his wording nor his real times and degrees belong in a committed
file, see *The one policy change* below:

```
➲ Sun <N> <month>
<hh:mm>  Moon at <d>° <sign> ▲          one line of meaning for the sign
<hh:mm>  Moon in the <n>th house ▲      one line of meaning for the house
Sun <N> <month>, <hh:mm> to <hh:mm>     void-of-course Moon in <sign>: meaning of the gap
Sun <N> <month>, <hh:mm>                Moon enters <sign>: meaning of the new programme
Sun <N> <month>, <hh:mm> to <hh:mm>
  ✤      <planet> in the 1st house is involved: meaning    (☽<d>°<sign> △ <planet><d>°<sign>)
Sun <N> <month>, <hh:mm> to <hh:mm>
  ✤✤✤✤✤  <planet> in the 12th house is involved: meaning   (☽<d>°<sign> ☍ <planet><d>°<sign>)
  Affects: my <planet> (−) ▲            the months-long transit, its meaning, its warning
```

Five things in that shape matter, and they are what the phases are built around:

- **The Moon drives the day.** Fast one-day configurations carry the content; slow transits
  are the background they land in. Our v1 did the opposite — it led with the season.
- **Every claim is timed**, with a start and an end, because the Moon changes the inner
  weather by the hour.
- **Intensity is published**, one to five `✤`, so a day has a shape rather than a flat list.
- **The formula is printed** next to the meaning. Nothing is unfalsifiable: the factor and
  its interpretation sit in the same line, which is what makes the text usable as an answer
  sheet at all.
- **Personal transits are flagged** (`Affects: my <planet> (−)`) and separated from the general
  Moon weather — a general window and a hit on the natal chart are different claims.

What the owner explicitly does *not* want copied is the **form**: «стиль у нього значно
гірше» (2026-10-30). The delivery stays ours — Ukrainian, for the ear, sixty to ninety
seconds, no figures spoken aloud. The method is his; the voice is ours.

## The one policy change

v1 carries a standing rule: *his readings never become content, only rules cross over*. Phase
1 suspends that rule for v2 and nothing else: his calendar for a day **is** the source of
that day's v2 reading, translated and compressed. The owner decided this, and it is the whole
point of phase 1 — you cannot learn to interpret a text you are forbidden to read out.

Two limits stay hard:

- **v1 is untouched** and keeps running at 08:15 until the owner says v2 replaces it (t1140).
  Both read the same day so the two can be compared.
- **Nothing of his is published.** His calendar is a paid personal product and it names his
  client's natal planets. It lives only in git-ignored state (`status/state/`), and committed
  files — this document included — describe its shape with every value replaced by a
  placeholder, never a quote.
- **He is not named in a committed file** (the owner's instruction, 2026-11-11). The repository
  is public; which astrologer he reads is his own business and not a part of this design. In
  code and documentation he is "the reference astrologer", and the quote above is elided for
  the same reason. Anything of his that must be kept under a recognisable name lives in
  `docs/personal/`, which is git-ignored.

## Phase 1 — read his finished calendar (t1143)

**Input:** his week, supplied by the owner (weekly, by hand). The intake already exists:
`astro_learn.py add --split` cuts a week into one entry per date, the Zirka chat classifies a
forwarded reading as `reference` rather than feedback, and `status/state/astro-reference-inbox/`
takes parked files. The store is `status/state/astro-reference.jsonl`, keyed by day.

**Output:** the day's reading for the owner, built *only* from his lines for that date:
Ukrainian, for the ear, the loud windows with their clock times, personal transits separated
from the general weather.

**Acceptance:** fidelity, measured both ways.
- Nothing invented: every statement in the output traces to a line of his text for that day.
- Nothing important dropped: every window he weighted `✤✤✤` or louder, and every
  `Affects: my <planet>` line, survives into the output.
- The reading is listenable by the rules v1 already obeys: no figures in the spoken part, no
  Latin script, no spoken headings, inside the character budget.
- His own verdict, after a week of it: better than v1, or not.

**Not in scope:** any astrology of our own. If his text for a date is missing, phase 1 says
so and sends nothing — it never fills the gap by computing a day itself. That silence is the
honest answer and also the thing that makes the phase measurable.

## Phase 2 — explain the same facts ourselves (t1144)

**Input:** the facts of a day with his meanings stripped off — the Moon's sign, house and
degree, the void-of-course window, the ingress, each timed aspect with its formula and
intensity, each personal transit. Taken from his own text at first (so the fact set is
identical and only the interpretation differs), and from `status/astro.py` once phase 3 can
produce the same list.

**Output:** our interpretation of each factor, then a graded comparison against his for that
same date.

**Acceptance:** per-factor agreement, counted rather than felt. For every factor in his text
for the day, our meaning is scored `same` / `close` / `opposite` / `missing`, and the result
is stored per day. The gate for moving on is a rate the owner sets after seeing the first
honest measurement — there is no point naming a target before the first number exists.

**The asset this phase builds** is a vocabulary: factor → meaning, every entry traceable to
the reference day it was learned from, append-only. The distillation prompt
(`status/mood/reference.md`) already emits exactly this under `Словник`, four entries at a
time; phase 2 turns that by-product into the main product and grows it to cover the factor
space (Moon in each sign, each house, each aspect to each body, void-of-course, ingress).

**Known trap, already paid for:** his hard aspects do not mean what the textbook says. A
square to Venus reads as indulgence and a pull towards comfort, not friction; the Moon in its
own sign reads as recovery, not neutral background. Both are already `ПРАВИЛО:` lines in
`status/state/astro-reference-rules.md`. Phase 2 is the machinery for finding the rest of
them systematically instead of one a week by accident.

## Phase 3 — choose the facts ourselves (t1145)

**Input:** a date, and nothing of his.

**Output:** the day's factor list computed here and ranked his way — the Moon's fast
configurations in the foreground with their windows and intensities, slow transits as
background, personal hits flagged.

**Acceptance:** selection overlap against his calendar for held-back dates. Of the windows he
names, how many did we compute and put in the same tier; and how many did we name that he
ignored. Both directions matter: a list that names everything is as useless as one that names
nothing.

**What has to be built**, because our ephemeris does not produce it yet:

| his calendar carries | we compute it | where |
|---|---|---|
| Moon by sign and degree | yes | `positions`, `sign_of` |
| Moon by house | yes | `house_of` |
| timed Moon aspects, sky and natal, with hold | yes | `moon_events` (t1060) |
| slow transits to natal points, with duration | yes | `transit_window` |
| retrogrades, Moon phase, dignities | yes | `day_sky`, `dignity` |
| **the ingress moment** (when the Moon changes sign) | no | needs a solver on the sign boundary |
| **the void-of-course window** (last aspect → ingress) | no | needs the ingress first |
| **a published intensity tier** (his one to five `✤`) | no | we score `1/(orb+0.5)` internally and never surface a tier |
| **which planet "is involved" and from which house** | partly | `body_state` says more than needed; the one-line form is missing |

The first three of those are arithmetic, so they are cheap and they are exactly what the
foreground of his day is made of.

## How any of this is measured

One method, three answer sheets. He supplies a week; the pipeline is scored on dates whose
text it was not shown.

- **Phase 1** — fidelity, as above: traceability and no loss. Mostly mechanical, so it can be
  tested rather than judged.
- **Phase 2** — per-factor agreement on a held-back date: `same` / `close` / `opposite` /
  `missing`, stored per day so a trend is visible rather than an impression.
- **Phase 3** — selection overlap on a held-back date, in both directions.

Everything is stored under `status/state/astro2/`, append-only, so a rule that improved the
numbers can be told from one that only sounded wise.

**The honest data position, 2026-11-11:** two days of his calendar are on file (30 October,
1 November) plus four non-calendar reference entries. Two days is enough to build phase 1 and
far too little to measure phase 2. Phase 2 scoring therefore waits on volume — roughly two
weeks of his text to say anything, a month before a rule learned from it is worth trusting.
If the owner has an archive of earlier weeks, feeding it in is the single fastest way to move
phases 2 and 3 forward; otherwise the calendar supplies about seven days a week and the
schedule follows from that.

## Where it all lives

Phase 0 is the scaffold already specified in `tasks/specs/t1140.md` and not yet built: its
own entry point (`status/mood2.py`), its own prompt directory (`status/mood2/`), its own log,
state and claims under an `astro2` config block, nothing on a timer, and a refusal to run at
all if that config block is missing — a silent fallback would let v2 write into v1's history.

```
status/mood2.py                     the v2 entry point, no timer until the owner says so
status/mood2/*.md                   the v2 prompts (phase 1: read, select, write)
status/state/astro2/                v2's own log, state, claims, agreement scores
status/state/astro2/vocabulary.md   factor → meaning, append-only, each entry sourced
status/state/astro-reference.jsonl  his calendar, by day (exists)
status/state/astro-reference-rules.md   rules distilled from it (exists, 96 lines)
```

## Roadmap

| step | task | what it delivers | blocked by |
|---|---|---|---|
| 0 | t1140 | the v2 scaffold: own entry point, prompts, state, no timer | — |
| 1 | t1143 | a daily reading built from his calendar, with fidelity tests | 0 |
| 2 | t1144 | our interpretation of his facts, scored per factor; the vocabulary | 1, and his text in volume |
| 3 | t1145 | the ingress, the void-of-course window, an intensity tier, and his ranking over our own facts | 2 |
| 4 | — | the switch: v2 takes the 08:15 slot, v1 is retired, after his verdict | 3 |

Phases 2 and 3 are gated by how much of his text is on file, not by how fast the code can be
written. Phase 1 is not — it can start now.

## Deliberately refused

- **Copying his sentences into a reading** past phase 1. Phase 1 reads his text because that
  is the lesson; phases 2 and 3 exist precisely so the output stops being a translation.
- **Copying his form.** Sixty to ninety seconds for the ear, not an hourly list read aloud.
- **Scraping his calendar.** It arrives when the owner sends it, by hand, weekly.
- **Merging sources.** The sky, the biorhythms and the weather stay three separate readings,
  as they are in v1.
