# The astro forecast, v1 — the record as it stands

Written on 2026-11-08 (t1140), the day the owner said of it: «та все ми не вірно зробили, це
не працює. Давай зараз запишемо все як є і зробимо паралельну версію».

This document is a **baseline**, not a design. It records what v1 is, what it was before, and
why each earlier shape was abandoned — so a v2 cannot rediscover a dead end as if it were a
new idea. Nothing here is an argument for keeping v1.

`docs/concept-mood.md` is the earlier version of this record and is **stale**: it describes
the six-stage, ~17-call pipeline that t1126 removed on 2026-11-01. Read it only as history.

---

## 1. What v1 sends

Two messages every morning at **08:15**, `noos-mood.timer` → `status/mood.py`:

- **astrology** — the reading, spoken by **Зоря** (profile `zorya-forecast`), sent through
  the **Zirka** bot;
- **biorhythms** — three sine values and a verdict, in the default voice, main chat.

They are deliberately two messages and two model calls. The owner's rule of 2026-10-28: one
source per reading. Merging them hid which claim came from where. The weather probe was
removed from the pipeline entirely for the same reason.

The `mood` probe shows the astrology, `bio` the biorhythms — two probes over one cached state
file, split in t1061 for the same reason.

---

## 2. The facts — computed, never asked for

`status/astro.py` (936 lines), Swiss Ephemeris via `pyswisseph`, built-in Moshier model: no
data files, ~0.01°, Placidus houses, tropical zodiac. Offline, free, identical every run. No
model touches a number.

Per day it computes:

| what | why it is there |
|---|---|
| the natal chart — positions, houses, each cusp's sign, its ruler and where the ruler stands, the chart's own aspects | the ground every transit is read against |
| the day's positions, retrogrades, the Moon's phase, the sky's own aspects | the day itself |
| which natal house each transiting body crosses | the aspect says what is touched, the house says where in a life |
| the transits to the natal chart, with orbs | the material |
| **the window of every transit** — `transit_window()` walks the ephemeris day by day over ±`window_days` (45): in-orb date, exact date, days held | separates a two-hour Moon trigger from a Saturn season, as arithmetic |
| **the day's focus** — each transit scores `1/(orb + 0.5)`, the score going to the moving body and to the house its natal target sits in; a body merely standing in a house adds half a point | the loudest planet and the leading house, without a model guessing |
| **each body's standing** — `body_state()`: function, sign, classical dignity, the house crossed, retrogradation, the aspects supporting and pressing it, what it does to the natal chart | a planet named in a reading has a full case behind it |
| the Moon's events **with clock times** | the one thing that makes a window checkable |
| the three biorhythm cycles (23 / 28 / 33 days), ported from lumi `core/biorhythm.py` | the second reading |

**A known correctness trap, already fixed:** the scan's edges are not the transit's edges. A
passage longer than ±45 days reads as «почалось до …, щонайменше до …», and an exactness
landing on the scan edge as «точність не раніше …». Printing the scan edge as a date was a
real defect, caught by the review stage.

Birth data is personal: `config.local.json` → `astro.birth` (date, time, zone **name** — the
historical UTC offset at a birth decades ago is usually not today's, which `zoneinfo` gets
right and a hardcoded number does not — place, lat/lon). Never in the committed config, never
quoted in documentation (t1053).

The written natal portrait is `status/state/natal.md` (git-ignored), added **beside** the
computed chart, never instead of it.

---

## 3. The pipeline — three model calls

Rebuilt in t1126 on 2026-11-01, from six stages and about seventeen calls down to three. The
docstring of `write_forecast()` states why: what the owner needs is not more material.

```
факти (локально, без моделі)  →  вибір  →  письмо  →  перевірка
```

1. **`pick.md`** (`astro.models.judge`) — the arc that holds for weeks, two or three
   **states** the day will carry, and what to do with them. Gets: natal chart, computed facts
   with windows, the Moon's clock events, the computed focus, the owner's life context, the
   calibration rules, yesterday's reading. A window must exist in the facts — timing is
   arithmetic, not invention.
2. **`day.md`** (`astro.models.final`) — the reading, for the ear, about `budget_chars`
   (config says 1400; CLAUDE.md still says 1200) characters, four spoken parts plus one
   unspoken:
   - `ДЕНЬ` — one sentence, the day's emotional colour, no planets, no figures;
   - `ПРОГНОЗ` — two or three lines, `вікно | тема | варіант або варіант або варіант`, ≤180
     characters;
   - `ДІЯ` — one line, what to do with those states;
   - `ДУГА` — one sentence, the long line and whether this is its peak;
   - `ОСНОВА` — the figures, in a block **the voice never reads** (`spoken()` drops it,
     `scrub_voice()` is the net under that).
3. **`check.md`** (`astro.models.review`) — returns the reading **corrected**, not critiqued:
   every line a state rather than an event, every window real, no figure in the spoken parts,
   the arc matching the computed duration, nothing silently contradicting yesterday.
   `corrected()` refuses a correction that lost the structure, so there is no fourth call.

Then, outside the three: `fit_budget()` (→ `compress.md` when over), `forecast_parts()`,
`claims()`, and for the voice only, `with_tags()` (→ `voice.md`) — one cheap call that places
one or two audio tags per paragraph. A render that changes the words by more than a sixth is
discarded. Sections are separated by sound, never by layout: `[довга пауза]` before a
heading, `[без емоцій]` on it, `[пауза]` after.

Plus one separate call, `bio.md` (`astro.models.judge`), for the biorhythms — forbidden to
name a planet.

Four or five calls and two to three minutes a morning, against seventeen and nine before.

### Every prompt file in `status/mood/`

| file | role | still in the main path? |
|---|---|---|
| `pick.md` | stage 1 — choose the arc and the states | yes |
| `day.md` | stage 2 — write the reading | yes |
| `check.md` | stage 3 — return it corrected | yes |
| `bio.md` | the biorhythm reading, no astrology in it | yes |
| `compress.md` | shorten an over-budget reading, structure kept | only when over budget |
| `voice.md` | place Зоря's audio tags, spoken copy only | yes, for the voice |
| `calibrate.md` | compare a day's forecast with what the owner said about it → `ПРАВИЛО:` | `mood_feedback.py calibrate` |
| `reference.md` | distil **interpretation** rules from a real astrologer's reading | `astro_learn.py learn` |
| `split.md` | cut a forwarded multi-day astrologer text into days | `astro_learn.py add` |

---

## 4. What a reading is about — the rules, and the three times they changed

This is the part a v2 must not relitigate blind.

**Iteration 1 — atmosphere.** «Напруга в комунікації». Abandoned 2026-11-01: nothing in it
could be checked or used, and the calibration loop had nothing to measure. The owner: «те, що
виходить, зовсім не працює і не дає ні прогнозу, ні читабельно».

**Iteration 2 — event prediction.** «До обіду розмова, де тебе перепитають». Abandoned the
same evening, by his correction: «зараз прогноз це як передбачування подій… але астрологія це
про інше. Астрологія показує які емоції і бажання будуть а не події. Що буде хотітись, що
буде нервувати, що буде захоплювати».

**Iteration 3 — states, which is v1.** What will pull, irritate, absorb; where there will be
drive and where nothing. An event is only one expression of a state — the same configuration
becomes a letter for one person, insomnia for another, a decision that finally ripened for a
third — which is why it cannot be predicted. The prompts forbid naming an event even as an
example, and a test guards that frame.

**Iteration 3b — one window, a family of states.** Also 2026-11-01: «це дуже однозначно, тому
що для кожного вікна може бути декілька інтерпретацій». So a line gives a **theme** and two
or three different ways it can be lived, joined by «або» — different in direction, not
rephrasings.

The standing shape rules, learned across 2026-10-27 and 2026-11-01:

- a forecast is a **checkable claim**, not an atmosphere; each carries a window and a sign;
  two or three, never more; two beats three if the third is vague;
- it is **made for the ear** — 60–90 seconds in one stream, no spoken headings, no figures
  outside `ОСНОВА`. A degree read aloud is what made the first version unlistenable;
- **no theory** — not "a square means tension", not "the eighth house is about…". He knows
  the vocabulary; the explanation is padding;
- **everyday anchors** — a claim lands in something recognisable, not in a mood;
- **dry irony, exactly one stroke**, in `ДЕНЬ` or `ДІЯ`. It colours, never softens: a bad day
  is called bad;
- **the arc says whether it is new** — the same line three days running is normal and is said
  to be the same; a new arc every morning would mean it is being invented;
- **time in words** in the spoken parts, figures only in `ОСНОВА`; a clock time is the one
  exception, because it is what makes a claim checkable;
- **biorhythms are one line of figures and one or two sentences**, and never a planet.

---

## 5. The calibration loop

A forecast nobody checks is decoration. The owner, 2026-10-27: «я це відчуваю по іншому ніж
ти подаєш».

1. **The claims are data.** Each state goes to `status/state/forecast-claims.jsonl` (day, id,
   window, claim, sign, verified). A second run of one morning replaces that day's set.
2. **Collection** — `mood_feedback.py add "<text>"` → `status/state/mood-feedback.jsonl`,
   append-only. Three ways in: `/feel`, the evening question, and the session writing it down
   whenever he says something about how a day felt.
3. **The evening question**, `noos-mood-ask.timer` at 21:00, built from that morning's stored
   claims with **no model involved** (t1126): one yes/no per claim, naming its window and
   sign, plus an invitation to say nothing of the sort happened — «не влучило» is worth more
   than «нормально». A model could only paraphrase, and paraphrasing turns a promise back
   into atmosphere. Skipped if he already spoke about the day after `ask_after_hour` (18:00).
   No claims means no question.
4. **Comparison** — `calibrate [--day]` → `ЗБІГЛОСЯ` / `РОЗІЙШЛОСЯ` / `ПРАВИЛО:`; rules
   accumulate in `status/state/mood-calibration.md`, append-only, a wrong rule superseded by
   a new line and never edited away. Run automatically for yesterday at the start of each
   morning.
5. **Feeding back** — `rules` returns the latest `rules_in_prompt` (8), injected into both
   `pick.md` and `day.md` with the instruction that a rule outranks the textbook. `score`
   reports the hit rate over `score_days` (14) — the first thing in this project that can
   judge whether a rule is worth keeping.

No remarks for a day means no calibration: inventing a correction out of silence is worse
than leaving the reading alone.

### Learning from a real astrologer

The owner forwards readings from an astrologer he rates as accurate into Zirka's chat
(2026-10-30). `zirka_intent.md` classifies such a message as `reference`, not feedback —
mistaking one for the other would poison the calibration. Stored in
`status/state/astro-reference.jsonl`, distilled by `reference.md` into `ТРАКТУВАННЯ` /
`РОЗХОДЖЕННЯ` / `ПРАВИЛО:` lines in `status/state/astro-reference-rules.md`.

**Only the interpretation is learned, never the style** («стиль у нього значно гірше, тут
важливо як він інтерпретує факти»). A rule about delivery — "start with the pressure", "write
shorter" — is explicitly rejected by the prompt. His sentences never become content: that
would be copying, and the two readings are built from different things — his from a sun sign,
ours from this chart's houses and transits. `calibration()` feeds the newest
`reference_rules_in_prompt` (6) in, **labelled separately** from the rules learned from his
own account of his days: one says how to read, the other whether we read *him* right.

---

## 6. Files, state and settings

| path | what |
|---|---|
| `status/mood.py` (801 lines) | the entry point: facts → three calls → two messages |
| `status/astro.py` (936) | the ephemeris, windows, focus, body states, biorhythms |
| `status/mood_feedback.py` (329) | collection, the evening question, calibrate, rules, score |
| `status/astro_learn.py` (304) | the reference astrologer: add, split, learn, rules |
| `status/mood/*.md` | the nine prompts above |
| `status/state/mood.log` | every run appended, one `===== YYYY-MM-DD =====` block a day — facts, pick, writing, check, biorhythms. Append-only, and the next day reads its own past there |
| `status/state/mood.json` | the cached summaries the `mood` and `bio` probes read |
| `status/state/forecast-claims.jsonl` | the claims, for the evening question and the score |
| `status/state/mood-feedback.jsonl` | what he said about his days |
| `status/state/mood-calibration.md` | the rules learned from that |
| `status/state/astro-reference.jsonl` / `-rules.md` | the other astrologer, and what was learned from him |
| `status/state/natal.md` | the written portrait (git-ignored) |
| `config.json` → `astro` | houses `P`, per-aspect orbs (6/6/5/5/3), `window_days` 45, `facts` caps (transits 10, sky 4), `models` per stage, `parallel` 5, `budget_chars` 1400, `rules_in_prompt` 8, `reference_rules_in_prompt` 6, `score_days` 14, `ask_after_hour` 18, `send_at` 08:15, `ask_at` 21:00, and every path above |
| `config.local.json` → `astro.birth`, `astro.subjects` | personal; never committed |

**More than one chart.** `astro.subjects.<name>` holds another person's `birth`, `natal_file`
and `context`; `--subject <name>` reads that chart and writes to its own `mood-<name>.log` /
`.json`, so one history never leaks into another. Кіра from matrix-agora is configured this
way. Calibration rules do **not** carry across subjects — they were learned from his account
of his days.

### Commands

```
status/astro.py --natal          the natal chart: positions, houses with rulers, aspects
status/astro.py --sky            today's sky, transits with houses, biorhythms
status/mood.py --facts           the computed facts with their windows, no model at all
status/mood.py --dry-run         the whole pipeline printed; nothing sent, nothing logged
status/mood.py --only bio|astro  one half of the morning
status/mood.py --resume          redo the writing from today's logged pick
status/mood.py --show            what was already read today
status/mood_feedback.py add "…" | ask | calibrate --day … | rules | score
status/astro_learn.py add "…" [--learn] | learn --day … | rules | list
```

Cost: about 5k characters of voice a day against the 1.8M monthly ElevenLabs quota (the
account is shared with lumi).

---

## 7. What v1 does right, and what it is accused of

Worth carrying into any v2, because each was bought with a defect:

- the numbers are **computed**, not asked of a model — a model handed real transits stops
  inventing them;
- every transit carries a **real duration**, so a Moon trigger is not sold as a season;
- the reading is **separable by source** — sky, biorhythms, weather never braided;
- the claims are **stored**, so an evening can ask about them and a score can exist;
- `ОСНОВА` is **never spoken**, so figures do not ruin the audio;
- calibration rules are **append-only** and outrank the textbook in the prompts.

The accusation, in his words on 2026-11-08: all of it is wrong and it does not work. What
specifically — content, form, or the whole idea of what a forecast is — is **not yet
recorded**, and that is the first thing v2 needs from him. This document does not guess it.
