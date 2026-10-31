# The morning forecast — how it works

Two messages every morning at 08:15: **biorhythms** and **astrology**. They are separate on
purpose — one is arithmetic from a birth date, the other is a sky, and merged into one
verdict it stops being visible which claim came from where.

Built on 2026-10-27 in a single sitting of about forty rounds of feedback. Most of what is
written below is a correction of something that was wrong first.

## 1. The numbers are computed, not asked for

`status/astro.py`, Swiss Ephemeris via `pyswisseph` (built-in Moshier model: no data files,
~0.01°, Placidus houses, tropical zodiac).

Computed per day:

- the natal chart — positions, houses, the sign on each cusp, its ruler and where that ruler
  stands, the aspects of the chart itself;
- the day's positions, retrogrades, the Moon's phase, the aspects in the sky;
- **which of his natal houses each transiting body is crossing** — the aspect says what is
  touched, the house says where in a life it happens;
- the transits to the natal chart, with orbs;
- **the window of every transit**: when it came into orb, when it is exact, how many days it
  holds. `transit_window()` walks the ephemeris day by day over ±45 days. This is what
  separates a two-hour Moon trigger (`тримається 1 дн`) from a Saturn season
  (`тримається 91 дн+`), and it is arithmetic, so nothing has to be guessed;
- **the day's focus**: each transit scores `1/(orb + 0.5)` — the tighter, the louder — and
  the score goes to the moving body and to the house its natal target sits in; a body merely
  standing in a house adds half a point. Out comes the loudest planet and the leading house;
- **each main body's standing**: function, sign, classical dignity (domicile, exaltation,
  detriment, fall), the house it crosses, retrogradation, the aspects supporting and pressing
  it, what it is doing to the natal chart;
- the three biorhythm cycles (23 / 28 / 33 days), ported from lumi `core/biorhythm.py`.

matrix-agora pays Gemini with Google Search for the same positions (`agents/sky.py`).
Computing them here is free, offline and identical every run — and a model handed real
transits stops inventing them. The one thing the ephemeris gave wrongly at first was the
scan window's edges being printed as the transit's edges; the review stage below caught it.

## 2. The pipeline

```
транзити поштучно  ┐
доми разом         ├→ зважування ─→ детальний черновик ─→ ревʼю ─→ стислий підсумок
Місяць окремо      │   (чутливість карти,                 (правки)
фон неба           ┘    тривалість, точність)
```

1. **Transits**, one model call each, in parallel. The sharp dated facts; one per call means
   none is dropped for being less interesting than another.
2. **Houses**, a single call over every placement at once with the house rulers. A house is
   about distribution — which area is loaded — and that is only visible with all twelve in
   view. Reading them one by one was the first version's worst mistake.
3. **The Moon**, its own call: phase, the house it crosses, what it lands on natally. It sets
   the emotional ground, so it never competes for a slot with a slow transit, and the summary
   must name it every time.
4. **The background**, one call for the retrogrades and the sky's own aspects — generational
   air rather than anybody's day.
5. **Weighing**, one call over the transits plus the three summaries. Ranks them by what hits
   *this* chart (planets on angles, loaded houses, natal aspects a transit re-opens) and by
   duration and exactness, from the position of a month or a quarter. Answers
   `ОСНОВНЕ` / `ФОН` / `ЧУТЛИВЕ` / `ЧОМУ`.
6. **The draft** — long and detailed, with every number. Nobody but the reviewer reads it.
7. **The review** — a strict editor checks the *draft*: does every claim rest on a named
   fact, is a one-day trigger sold as a season, are there signs or degrees the facts never
   mentioned, does it contradict yesterday, is the Moon there, is there padding or advice.
   Reviewing the short version would be reviewing prose; reviewing the long one catches the
   claim with no fact behind it. On its first run it found three real defects in the code.
8. **The summary** — applies the edits and compresses to what is actually sent.

Plus one separate call for the biorhythms, which never mentions astrology. About seventeen
calls and 7-9 minutes a morning.

Continuity: `yesterday_block()` parses the previous day's summary out of the log and hands it
to the draft, the review and the summary, so a day inside a three-month passage is not
announced as news.

## 3. What is actually sent

Four blocks, in this order, and the order is the point — the day first, the arithmetic last.

- **Коротко** — two or three sentences: the whole day and what to watch. The only block where
  advice belongs. No planets, no houses, no figures.
- **Опис дня** — three or four short sentences: which planet sets the tone, which house is the
  arena, where it is easy, where friction builds, the daily mood.
- **Історія дня** — the detailed half, and the hardest-won part. **Thesis first, cause
  second:** each of the three paragraphs opens with what happens in his life, in plain words
  with concrete examples, and only then says «це тому що Венера ретроградна — а це повернення
  до минулих прив'язаностей», with the fact glossed in the same breath and its time depth
  after it: when the line began, how much is left, and one or two hooks at what has not
  ripened yet. The ratio is **80/20** — four sentences of life to one of cause. A paragraph
  that opens with a planet's name is wrong. Houses and planets are always glossed from a
  fixed table, so «восьмий дім — спільні ресурси, борги» reads the same every morning.
- **Головне, на чому це стоїть** — the reference, and the only place with degrees and dates.
- **Насамкінець** — three flat lines, statements rather than advice: `Важливе` (what will
  remain of the day), `Приємне`, `Неприємне`. No astrology, no numbers, no «варто».

Length is a budget, not a wish: 300 / 400 / 1800 / 450 characters, 3000 in total. Over by
more than a fifth and one extra call cuts it, keeping the markers and the order. Nothing is
truncated mechanically.

Irony is required — exactly one dry stroke in `Коротко` and one in `Опис дня`. It colours the
observation and never softens it: a bad day gets bitter irony, not cheer.

## 4. The voice

**Зоря** — a voice designed for this on 2026-10-27 through ElevenLabs Voice Design from a
written description, chosen by ear out of three previews, saved to the account as
`Zorya — UA forecast`. For the forecast she is a Sagittarius: active, cheerful, quick,
curious. The content stays honest; the delivery is not a funeral.

- Profile `zorya-forecast`: `eleven_v4_turbo`, stability 0.2, style 0.6, tempo 1.1, tags on.
- **Audio tags are performed, not read** — but only by `eleven_v3`/`v4`;
  `eleven_multilingual_v2` (everything else Noos says) reads them out as words.
- **Tags are inserted by a separate render call**, never by the writer: a model asked to write
  and perform at once overacts. The text message stays clean; only the spoken copy carries
  tags. If the render changes the words by more than a sixth, it is discarded.
- **Sections are separated by sound**: `[довга пауза]` before each heading, `[без емоцій]` on
  the heading, `[пауза]` after. Two pause tags buy about three seconds of real silence;
  `<break time="…"/>` does nothing on this model.
- **`speed` is inert on v3/v4** (measured: 5.28 s at every setting from 1.0 to 1.5, while
  multilingual_v2 goes 5.34 → 3.81). So tempo is applied after synthesis with `atempo` in
  `voice/to_ogg.py`.
- The voice goes out **first**, as its own message, and the text follows: synthesis takes
  about a minute, and he listens rather than reads.

## 5. The feedback loop

A forecast nobody checks is decoration, and he feels his days differently from how they were
being presented. So:

1. **21:00 — the evening question**, in Зоря's voice. Not "how was your day" but the diary
   version: one call turns two or three of that morning's specific claims into questions that
   can be answered yes or no, each carrying a concrete example so there is something to catch
   on. Skipped if he already said something about the day after 18:00.
2. **Collection** — every remark lands in `status/state/mood-feedback.jsonl`, append-only.
   Three ways in: the evening question, `/feel <text>`, and the session writing down whatever
   he says about how a day felt, voice messages included.
3. **Comparison** — each morning, before the new reading, yesterday's forecast is put next to
   yesterday's remarks: `ЗБІГЛОСЯ` / `РОЗІЙШЛОСЯ` / `ПРАВИЛО:`. The rules accumulate in
   `status/state/mood-calibration.md`, append-only; a rule that proves wrong is superseded by
   a new line, never edited away.
4. **Correction** — the latest eight rules are injected into three stages (weighing, draft,
   summary) with the instruction that a rule outranks the textbook. A rule has to be
   actionable: not "be more accurate" but «для цієї карти Місяць в опозиції до Сонця дає
   менше, ніж здається — не виносити його в головне».

No remarks for a day means no calibration. Inventing a correction out of silence is worse
than leaving the reading alone.

## 6. Where everything lives

```
status/astro.py                 the ephemeris: chart, windows, focus, dignities, glosses
status/mood.py                  the pipeline, the messages, the voice
status/mood_feedback.py         the evening question, the feedback store, the calibration
status/mood/*.md                nine prompts: fact, houses, moon, background, rank,
                                draft, review, summary, compress, voice, ask, calibrate
status/probes/mood.py           the `mood` probe — repeats today's reading for free
status/state/natal.md           the written natal portrait (git-ignored, personal)
status/state/mood.log           every run, every stage, append-only
status/state/mood.json          today's summaries, for the probe and /mood
status/state/mood-feedback.jsonl
status/state/mood-calibration.md
config.json          → astro.*, voice.profiles.*, voice.roles.*  (neutral defaults)
config.local.json    → astro.birth, the real voice roster        (personal, git-ignored)
```

Timers: `noos-mood.timer` 08:15, `noos-mood-ask.timer` 21:00.

Commands: `/mood` repeats today's reading, `/feel <text>` records how the day felt.

```
status/mood.py --facts           the computed facts with their windows, no model at all
status/mood.py --dry-run         the whole pipeline printed; nothing sent, nothing logged
status/mood.py --only bio|astro  one half of the morning
status/mood.py --resume          redo only the summary from today's logged draft and review
status/mood_feedback.py rules    the rules the prompts are currently obeying
```

## 7. Other charts

`astro.subjects.<name>` configures someone else's `birth`, `natal_file` and `context` — the
life the story's examples must come from, since a forecast that lands in the wrong life is
just prose. `mood.py --subject <name>` runs the whole pipeline on that chart and writes to
`mood-<name>.log` / `mood-<name>.json`, so histories never mix. Calibration rules stay with
the owner: they were learned from his account of his own days and say nothing about another
chart.

Кіра from matrix-agora was the first: her chart comes out of the ephemeris (Sun Sagittarius
10° in V, Moon Scorpio 19° in IV, ASC Leo 16°, MC Taurus 1° — matching the canon snapshot her
agent already carries), her natal file is read straight from `canon/kira.natal.md`, her
examples come from the planetarium, the observatory, the mountains and kintsugi, and her
forecast is spoken in her own Agora voice.
