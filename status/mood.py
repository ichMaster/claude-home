#!/usr/bin/env python
"""The morning forecast — biorhythms and astrology, as two separate readings.

They are two different things and the owner wants them apart (2026-10-27): biorhythms are
three sine curves from a birth date, astrology is a sky; mixed into one verdict, it stops
being visible which claim came from which. So two messages go out, each with its own voice.

The astrology half is a **pipeline of model calls in layers**, not one call and not a flat
list of atoms. The shape is the owner's (2026-10-27), and the layering is the fix to the
first version: when all 26 facts were read one by one, "Mars opposite your ASC" and "Mars
crossing your 7th" went to two calls that could not see each other, and houses suffered
most — a house is about distribution, which is only visible with all twelve in view.

    transits, one by one  ┐
    houses, all together  ├→  weigh by natal sensitivity  →  write with arguments
    the Moon, on its own  │   and by duration/exactness
    the background        ┘

1. `status/astro.py` computes the day and tags every fact with its `layer`: each transit to
   a natal point (with its window — when it came into orb, when it is exact, how many days
   the passage holds), each transiting body standing in a natal house, the Moon in all its
   forms, the retrograde set, the sky's own aspects.
2. **Transits** — one call per transit, in parallel. These are the sharp, dated facts, and
   one per call means none is quietly dropped because another was more interesting.
3. **Houses** — a single call over every placement at once, with the house rulers: where
   the load is, which areas are quiet, what is background and what is today.
4. **The Moon** — its own call: the phase, the house it crosses, what it lands on natally.
   It sets the emotional ground of the day, so it never competes for a slot with a slow
   transit, and the summary must name it every time.
5. **The background** — one call for the retrogrades and the sky's own aspects, which are
   generational air rather than anybody's day.
6. **Weighing** — one call over the transits plus the three summaries, ranking them by what
   hits *this* chart (ЧУТЛИВЕ — planets on angles, loaded houses, natal aspects a transit
   re-opens) and by duration and exactness. Answers ОСНОВНЕ / ФОН / ЧУТЛИВЕ / ЧОМУ.
7. **Writing** — ГОЛОВНЕ (one to three facts that carry the day, each with why it matters)
   and ПІДСУМОК (the day in three or four sentences, each followed by the fact it stands
   on). Short on purpose: he asked not to be sent the whole fact list.

Why the split pays: a single call has to invent its own sense of weight, and it reliably
mistakes the exact-today Moon for the news of the day. The weighing stage is handed the
arithmetic — «тримається 91 дн, точно зараз» against «тримається 1 дн» — so the ranking
has a basis. The full fact list with every reading stays in the log.

The numbers never come from a model: `astro.py` computes them from the Swiss Ephemeris. A
model handed real positions stops inventing them.

**IMPORTANT** about the headless calls: the Telegram plugin must be off
(`status/digest-settings.json`), or a second session hijacks `getUpdates` and the main one
stops seeing messages. These calls need no connectors, so MCP is stripped too.

    mood.py                 today: compute, read, send both messages
    mood.py --day 2026-10-27
    mood.py --dry-run       the whole pipeline, printed; nothing sent, nothing logged
    mood.py --facts         just the computed facts, no model at all
    mood.py --show          what was already read today
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path  # noqa: E402

import astro  # noqa: E402  — same directory
import mood_feedback  # noqa: E402  — the calibration rules
import astro_learn    # noqa: E402  — the rules learned from a real astrologer's readings

HOME = Path(__file__).resolve().parents[1]
PROMPTS = HOME / "status" / "mood"
SETTINGS = HOME / "status" / "digest-settings.json"
FACT_TIMEOUT = 180      # one short interpretation
CALL_TIMEOUT = 420      # the weighing and the writing are longer

_BLOCK_RE = re.compile(r"^[\s*#_>•·—-]*(ЧИТАННЯ|КОРОТКО|ГОЛОВНЕ|ФАКТИ|ПІДСУМОК|ІСТОРІЯ|НАСАМКІНЕЦЬ|ЧОМУ|ПРАВКИ|ОЦІНКА|ПОКАЗНИКИ|ВИСНОВОК)[\s*_#]*:?[\s*_#]*(.*)$",
                       re.IGNORECASE | re.MULTILINE)
_ID_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9_-]+")


def today() -> date:
    return datetime.now(ZoneInfo(conf("astro.tz", "Europe/Kyiv"))).date()


def plain(text: str) -> str:
    """Drop Markdown emphasis — Telegram gets plain text, so a stray `**` shows literally."""
    return re.sub(r"\*+", "", text or "").strip()


# --- the model calls -----------------------------------------------------------------------------------------------

def run_claude(prompt: str, model: str = "", timeout: int = CALL_TIMEOUT) -> str:
    """One headless call. An empty `model` means the session default — the strongest one."""
    cmd = ["claude", "-p", prompt, "--settings", str(SETTINGS),
           "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config"]
    if model:
        cmd += ["--model", model]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         cwd=str(HOME), stdin=subprocess.DEVNULL)
    if out.returncode != 0:
        raise RuntimeError(f"виклик не вдався (код {out.returncode}): {out.stderr.strip()[:300]}")
    return out.stdout.strip()


def fill(name: str, **values: str) -> str:
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value or "")
    return text


def split_blocks(text: str) -> dict[str, str]:
    """`ФАКТИ:` / `ПІДСУМОК:` (or `ПОКАЗНИКИ:` / `ВИСНОВОК:`) → a dict of blocks."""
    marks = list(_BLOCK_RE.finditer(text))
    blocks: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        inline, below = m.group(2).strip(), text[m.end():end].strip()
        blocks[m.group(1).upper()] = "\n\n".join(p for p in (inline, below) if p).strip()
    return blocks


# --- the pipeline --------------------------------------------------------------------------------------------------

def calibration() -> str:
    """The rules distilled from his own account of past days.

    They go into the weighing, the draft and the summary, because that is the only way a
    miss changes anything: «я це відчуваю по іншому ніж ти подаєш» (2026-10-27). Empty until
    the first day has been compared.
    """
    if astro.SUBJECT:
        # the rules were learned from HIS account of HIS days; they say nothing about anyone
        # else's chart, so another subject starts uncalibrated
        return "правил поки немає"
    own = mood_feedback.rules(int(conf("astro.rules_in_prompt", 8)))
    # rules learned from a real astrologer's readings: how to read, as opposed to whether we
    # read *him* right. Marked separately so a stage can tell the two apart
    ref = astro_learn.rules(int(conf("astro.reference_rules_in_prompt", 6)))
    parts = []
    if own:
        parts.append("З його власних відгуків про дні:\n" + own)
    if ref:
        parts.append("З прогнозів астролога, якого він вважає точним (як читати):\n" + ref)
    return "\n\n".join(parts) or "правил поки немає"


def reference_block(day: date) -> str:
    """The other astrologer's reading for this very day, when he has sent one ahead.

    He forwards the hourly calendar a week in advance so the pipeline can **cross-check
    while it generates** (2026-10-31: «вона може дивитись чи вже був еталон на цей день і
    звірятись»). It is given to the weighing and to the review, and nowhere else: those two
    stages decide what is loud and whether a claim stands, which is exactly where a missed
    factor shows. It is a checklist, never a source — the draft and the summary never see it,
    so nothing of his wording can leak into what gets sent.
    """
    if astro.SUBJECT:
        return "(еталона немає)"                  # his astrologer reads his chart, not theirs
    text = astro_learn.for_day(day)
    return text.strip() if text else "(еталона на цей день немає)"


def state_path(key: str) -> Path:
    """A state file for whoever is being read: the owner keeps `mood.log`, a named subject
    gets `mood-<subject>.log`, so one chart never writes into another's history."""
    p = path(f"astro.{key}")
    if astro.SUBJECT:
        p = p.with_name(f"{p.stem}-{astro.SUBJECT}{p.suffix}")
    return p


def life_context() -> str:
    """Whose day the examples should come from.

    The story has to land in a life someone recognises, and that life is different for
    every subject — so it is configured (`astro.context` for the owner,
    `astro.subjects.<name>.context` for anyone else) rather than written down here. Both
    fall back to an instruction rather than to a description: a life sketch is personal and
    belongs in `config.local.json`, which never enters this public repository (t1053).
    """
    key = f"astro.subjects.{astro.SUBJECT}.context" if astro.SUBJECT else "astro.context"
    return (conf(key)
            or "про цю людину нічого не відомо — пиши загальними побутовими прикладами")


def natal_text() -> str:
    """The computed chart (positions, houses with their rulers, aspects) plus the portrait.

    The portrait never replaces the computed part — it used to, and that quietly hid the
    house table from the call (2026-10-27).
    """
    computed = astro.natal_lines(astro.natal_chart())
    if astro.SUBJECT:
        # a named subject may only have their OWN portrait: falling back to the owner's
        # file contaminated their reading with his chart description (t1051)
        natal_file = conf(f"astro.subjects.{astro.SUBJECT}.natal_file")
    else:
        natal_file = astro.subject_conf("natal_file", "status/state/natal.md")
    if not natal_file:
        return computed
    f = Path(str(natal_file)).expanduser()
    if not f.is_absolute():
        f = HOME / f
    if f.is_file():
        lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
        portrait = "\n".join(ln for ln in lines
                             if not ln.startswith(("Народження:", "Сонце ", "Молодий серп"))).strip()
        if portrait:
            return f"{computed}\n\nПортрет карти:\n{portrait}"
    return computed


_LOG_DAY_RE = re.compile(r"(?m)^===== (\d{4}-\d{2}-\d{2}) =====[ \t]*$")


def logged_sections(day: date) -> dict[str, str]:
    """The sections of today's logged run — `факти`, `черновик`, `ревʼю`, …

    Everything a run produces is already in the log, so re-running only the last stage
    (`--resume`) costs one call instead of seventeen. Prompt tuning is iterative; paying
    for the whole pipeline each time is not.
    """
    f = state_path("log")
    if not f.is_file():
        return {}
    text = f.read_text(encoding="utf-8")
    all_marks = list(_LOG_DAY_RE.finditer(text))
    sections: dict[str, str] = {}
    # Newest first, and an older block may still hold a section the newest lacks: a resumed
    # run appends only the summary it redid, so the draft lives in the block before it.
    for i in range(len(all_marks) - 1, -1, -1):
        if all_marks[i].group(1) != day.isoformat():
            continue
        end = all_marks[i + 1].start() if i + 1 < len(all_marks) else len(text)
        for m in re.finditer(r"--- (.+?) ---\n(.*?)(?=\n--- |\Z)",
                             text[all_marks[i].end():end], re.DOTALL):
            sections.setdefault(m.group(1), m.group(2).strip())
    return sections


def yesterday_block(day: date) -> str:
    """The last reading logged before `day`, as a short note for the next one.

    Continuity matters: a day inside a three-month Saturn passage is not news, and a
    forecast that contradicts yesterday without saying so is just noise. The log is the
    only store, so this parses it rather than keeping a second copy.
    """
    f = state_path("log")
    if not f.is_file():
        return ""
    text = f.read_text(encoding="utf-8")
    all_marks = list(_LOG_DAY_RE.finditer(text))
    marks = [m for m in all_marks if m.group(1) < day.isoformat()]
    # Newest first, and keep walking back: a --resume run appends a block holding only
    # `підсумок (перероблено)`, which the old single-block regex missed, so the morning
    # after any resume silently lost yesterday's context (t1051).
    for last in reversed(marks):
        end = next((m.start() for m in all_marks if m.start() > last.end()), len(text))
        block = text[last.end():end]
        final = re.search(r"--- (?:підсумок(?: \(перероблено\))?|прогноз) ---(.*?)(?=\n--- |\Z)",
                          block, re.DOTALL)
        body = split_blocks(final.group(1)) if final else {}
        summary = body.get("ПІДСУМОК") or ""
        if summary:
            return (f"Учорашній прогноз ({last.group(1)}) — щоб не суперечити собі й сказати, "
                    f"якщо лінія триває:\n{summary.strip()[:1200]}")
    return ""


def interpret_facts(natal: str, day: date, facts: list[dict], note=lambda *a: None) -> list[dict]:
    """Stage 2 — one call per fact, in parallel.

    A fact whose call fails keeps its text and loses only its interpretation: one broken
    transit must not cost the whole day.
    """
    model = conf("astro.models.fact", "sonnet")
    workers = int(conf("astro.parallel", 5))

    def one(f: dict) -> dict:
        prompt = fill("fact.md", НАТАЛ=natal, ДАТА=day.isoformat(),
                      ФАКТ=f["text"], ВІКНО=f.get("window_text", ""))
        try:
            return {**f, "reading": plain(run_claude(prompt, model, FACT_TIMEOUT))}
        except Exception as e:
            note(f"  факт {f['id']} не прочитався: {e}")
            return {**f, "reading": ""}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, facts))


def summarise_layer(name: str, prompt: str, natal: str, day: date, facts: list[dict],
                    label: str, extra: dict[str, str] | None = None,
                    note=lambda *a: None) -> dict | None:
    """One call over a whole layer (the houses, the Moon, the background) → a fact-shaped
    dict, so the weighing and writing stages treat a summary exactly like an atom."""
    if not facts:
        return None
    body = "\n".join(f["text"] + (f" [{f['window_text']}]" if f.get("window_text") else "")
                      for f in facts)
    try:
        reading = plain(run_claude(fill(prompt, НАТАЛ=natal, ДАТА=day.isoformat(),
                                        **{name: body}, **(extra or {})),
                                   conf("astro.models.layer", "sonnet"), CALL_TIMEOUT))
    except Exception as e:
        note(f"  шар {label} не прочитався: {e}")
        return None
    return {"id": label, "kind": "layer", "layer": label.lower(), "text": body,
            "window_text": "", "reading": reading}


def fact_lines(facts: list[dict]) -> str:
    """The facts as the weighing call reads them: id, the fact, its window, its reading."""
    out = []
    for f in facts:
        window = f" [{f['window_text']}]" if f.get("window_text") else ""
        out.append(f"{f['id']}: {f['text']}{window}\n    {f.get('reading', '')}".rstrip())
    return "\n".join(out)


def weigh(natal: str, day: date, facts: list[dict]) -> dict:
    """Stage 3 — rank the facts from the position of a month or a quarter."""
    answer = run_claude(fill("rank.md", НАТАЛ=natal, ДАТА=day.isoformat(),
                             КАЛІБРУВАННЯ=calibration(),
                             ЕТАЛОН=reference_block(day),
                             ФАКТИ=fact_lines(facts)),
                        conf("astro.models.judge", ""))
    known = {f["id"] for f in facts}

    def ids(label: str) -> list[str]:
        m = re.search(rf"^[\s*#_>-]*{label}[\s*_#]*:(.*)$", answer, re.MULTILINE | re.IGNORECASE)
        return [i for i in _ID_RE.findall(m.group(1)) if i in known] if m else []

    main, back, tender = ids("ОСНОВНЕ"), ids("ФОН"), ids("ЧУТЛИВЕ")
    why = re.search(r"^[\s*#_>-]*ЧОМУ[\s*_#]*:(.*)", answer, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not main:                                   # the markers went missing — keep the computed order
        main = [f["id"] for f in facts[:4]]
        back = [f["id"] for f in facts[4:12]]
    return {"main": main, "background": [i for i in back if i not in main],
            "tender": tender, "why": plain(why.group(1)) if why else "", "raw": answer}


def _chosen(by_id: dict[str, dict], ids: list[str]) -> str:
    """The picked facts with their windows and readings, as the final call reads them."""
    return "\n".join(
        by_id[i]["text"]
        + (f" [{by_id[i]['window_text']}]" if by_id[i].get("window_text") else "")
        + (f"\n    {by_id[i]['reading']}" if by_id[i].get("reading") else "")
        for i in ids if i in by_id)


BLOCKS_SENT = ("КОРОТКО", "ПІДСУМОК", "ІСТОРІЯ", "ГОЛОВНЕ", "НАСАМКІНЕЦЬ")


def fit_budget(answer: str, note=lambda *a: None) -> str:
    """One extra call if the result overshoots the length budget.

    The prompt carries per-block limits, but a model that is enjoying itself drifts past
    them, and the owner reads these aloud — «все одно довше виходить» (2026-10-27). Rather
    than truncate mid-sentence, ask once for a cut. Over by a little is left alone; the
    call only pays for itself when the overshoot is real.
    """
    limit = int(conf("astro.budget_chars", 2400))
    blocks = split_blocks(answer)
    size = sum(len(blocks.get(k, "")) for k in BLOCKS_SENT)
    note(f"    довжина: {size} знаків (ліміт {limit})")
    if size <= limit * 1.2:
        return answer
    try:
        shorter = run_claude(fill("compress.md", ЗАРАЗ=str(size), ЛІМІТ=str(limit),
                                   ТЕКСТ=answer), conf("astro.models.final", ""))
    except Exception as e:
        note(f"    скорочення не вдалося: {e}")
        return answer
    got = split_blocks(shorter)
    if not got.get("КОРОТКО") and not got.get("ПІДСУМОК"):
        return answer                             # the cut lost the structure — keep the original
    note(f"    після скорочення: {sum(len(got.get(k, '')) for k in BLOCKS_SENT)} знаків")
    return shorter


def summary_call(day: date, facts_text: str, moon_text: str,
                 draft: str, fixes: str, before: str) -> str:
    """The last stage on its own: apply the review's edits and compress to what is sent."""
    return run_claude(fill("summary.md", ДАТА=day.isoformat(),
                           КАЛІБРУВАННЯ=calibration(),
                           ФОКУС=astro.focus_lines(astro.day_focus(day), day),
                           ЗНАЧЕННЯ=astro.glossary_lines(),
                           КОНТЕКСТ=life_context(),
                           ФАКТИ=facts_text, МІСЯЦЬ=moon_text,
                           ЧЕРНОВИК=draft, ПРАВКИ=fixes, УЧОРА=before),
                      conf("astro.models.final", ""))


def write_forecast(natal: str, day: date, facts: list[dict], rank: dict,
                   note=lambda *a: None, partial: dict | None = None) -> dict[str, str]:
    """The last three stages: a detailed draft, a review of it, then the short result.

    The owner's shape (2026-10-27): the draft is written long and the review checks *it* —
    not the summary — against the facts, and only then is everything compressed to what
    actually gets sent. Reviewing the short version would be reviewing prose; reviewing the
    long one catches the claim that has no fact behind it.

    `partial`, when given, receives each stage's output as it is produced, so a failed call
    does not discard the stages already paid for — the caller logs it and --resume can pick
    the draft up (t1051).
    """
    by_id = {f["id"]: f for f in facts}
    # The Moon always reaches the writing stages, whatever the ranking said: it sets the
    # day's emotional ground, and the owner wants it in the summary every time.
    moon = [f["id"] for f in facts if f["id"] == "МІСЯЦЬ" or f.get("layer") == "moon"]
    before = yesterday_block(day)
    model = conf("astro.models.final", "")

    note("    черновик")
    draft_raw = run_claude(fill("draft.md", НАТАЛ=natal, ДАТА=day.isoformat(),
                                ФОКУС=astro.focus_lines(astro.day_focus(day), day),
                                ЗНАЧЕННЯ=astro.glossary_lines(),
                                КОНТЕКСТ=life_context(),
                                КАЛІБРУВАННЯ=calibration(),
                                ОСНОВНЕ=_chosen(by_id, rank["main"]),
                                ФОН=_chosen(by_id, [i for i in rank["background"] if i not in moon]),
                                МІСЯЦЬ=_chosen(by_id, moon),
                                ЧУТЛИВЕ=_chosen(by_id, rank.get("tender", [])),
                                ЧОМУ=rank["why"], УЧОРА=before),
                           model)
    draft = plain(split_blocks(draft_raw).get("ЧИТАННЯ", "")) or plain(draft_raw)
    if partial is not None:
        partial["черновик"] = draft

    note("    ревʼю")
    review_raw = run_claude(fill("review.md", ДАТА=day.isoformat(),
                                 ФАКТИ=fact_lines(facts), ЗВАЖУВАННЯ=rank["raw"],
                                 ЕТАЛОН=reference_block(day),
                                 ЧЕРНОВИК=draft, УЧОРА=before),
                            conf("astro.models.review", ""))
    review = split_blocks(review_raw)
    if partial is not None:
        partial["ревʼю"] = review_raw
    fixes = plain(review.get("ПРАВКИ", "")) or "немає"
    note(f"    оцінка: {plain(review.get('ОЦІНКА', ''))[:120]}")

    note("    підсумок")
    answer = fit_budget(summary_call(day, fact_lines(facts), _chosen(by_id, moon),
                                     draft, fixes, before), note)
    blocks = split_blocks(answer)
    return {"main": plain(blocks.get("ГОЛОВНЕ", "")), "summary": plain(blocks.get("ПІДСУМОК", "")),
            "lead": plain(blocks.get("КОРОТКО", "")),
            "story": plain(blocks.get("ІСТОРІЯ", "")),
            "closing": plain(blocks.get("НАСАМКІНЕЦЬ", "")),
            "draft": draft, "review": review_raw, "fixes": fixes, "raw": answer}


def write_biorhythms(day: date, bio: str) -> dict[str, str]:
    """The other forecast — the biorhythms alone, with no astrology in it at all."""
    answer = run_claude(fill("bio.md", ДАТА=day.isoformat(), БІОРИТМИ=bio),
                        conf("astro.models.judge", ""))
    blocks = split_blocks(answer)
    return {"figures": plain(blocks.get("ПОКАЗНИКИ", "")),
            "conclusion": plain(blocks.get("ВИСНОВОК", "")), "raw": plain(answer)}


# --- what goes out -------------------------------------------------------------------------------------------------

def bio_message(day: date, bio: dict, computed: str) -> str:
    body = "\n\n".join(p for p in (bio["figures"], bio["conclusion"]) if p) or bio["raw"]
    return f"🜛 Біоритми на {day.strftime('%d.%m')}\n\n{body}\n\nПораховано: {computed}"


def astro_message(day: date, forecast: dict) -> str:
    """The point first, then the day, the arithmetic last (the owner, 2026-10-27).

    The summary is the air of the day written as prose — no figures, no planet names, no
    dates. Then two or three sentences of why, in general terms. Then, at the end, the
    facts that were picked, where numbers are allowed. The full fact list stays in the log.
    """
    parts = [f"🜚 Астрологія на {day.strftime('%d.%m')}"]
    if forecast.get("lead"):                      # the whole day in two sentences, up front
        parts.append(forecast["lead"])
    if forecast["summary"]:
        parts.append(f"Опис дня\n{forecast['summary']}")
    if forecast.get("story"):
        parts.append(f"Історія дня\n{forecast['story']}")
    if forecast["main"]:
        parts.append(f"Головне, на чому це стоїть\n{forecast['main']}")
    if forecast.get("closing"):                   # a flat statement of the day, not advice
        parts.append(forecast["closing"])
    return "\n\n".join(parts) if len(parts) > 1 else f"{parts[0]}\n\n{plain(forecast['raw'])}"


def spoken(text: str) -> str:
    """What the voice reads: the message without its header line of symbols and the
    computed row of signed numbers, neither of which survives being read aloud."""
    body = [p for p in text.split("\n\n")[1:] if not p.startswith("Пораховано:")]
    return "\n\n".join(body).strip() or text


def with_tags(text: str, note=lambda *a: None) -> str:
    """Insert ElevenLabs audio tags into what will be spoken — the render layer.

    Separate from writing, deliberately (`docs/voice-emotion.md` §4.4): a model that is
    asked to write *and* perform overacts, so the summary writes plain text and one cheap
    call places one or two tags per paragraph, before the clause each governs. The tags
    never touch the text message — only the spoken copy — because `eleven_multilingual_v2`
    (everything else Noos says) would read them out as words.

    Verified on Ада's voice with `eleven_v4_turbo`, 2026-10-27: a tagged take came back
    13.4 s against 9.9 s plain, and Deepgram found no tag word in the transcript — they
    were performed, not spoken. `[довга пауза]` and `[пауза]` give real silence (+3 s for
    two of them) and are what separates the sections audibly; `<break time="…"/>` does
    nothing at all on this model, so it is not used.
    """
    try:
        out = plain(run_claude(fill("voice.md", ТЕКСТ=text),
                               conf("astro.models.layer", "sonnet"), FACT_TIMEOUT))
    except Exception as e:
        note(f"    теги не вставилися: {e}")
        return text
    # a render that lost the words is worse than no tags at all
    bare = re.sub(r"\[[^\]]{1,40}\]", "", out)
    if abs(len(bare) - len(text)) > max(80, len(text) * 0.15):
        note("    теги відкинуті: текст змінився")
        return text
    return out


def send(text: str, role: str = "mood", note=lambda *a: None) -> None:
    """Voice first as its own message, then the text.

    A full reading is several Telegram messages and about a minute of synthesis, so one
    combined call lands the text long before the voice — and he listens rather than reads
    (2026-10-27: «ти не зробив голосове», sent while the audio was still being made).

    The voice comes from the role's profile (`voice.roles.mood` → Ада on `eleven_v4_turbo`),
    which is also what makes audio tags possible: a different voice and a performed delivery
    say what kind of message this is before a word of it is understood.
    """
    notify = str(HOME / "notify.sh")
    profile = conf(f"voice.roles.{role}")
    settings = conf(f"voice.profiles.{profile}") or {} if profile else {}
    body = spoken(text)
    if settings.get("tags"):
        body = with_tags(body, note)
    voice = ["--voice-profile", role] if profile else []
    # The reading goes to its own bot when one is configured (`telegram.bots.mood`): a
    # forecast is several messages and a minute of audio, and it buried the conversation
    # in the main chat. notify.sh falls back to the main bot if the token is missing.
    bot = ["--bot", role] if conf(f"telegram.bots.{role}") else []
    subprocess.run([notify, *bot, *voice, "--voice-only", body],
                   check=False, cwd=str(HOME), timeout=300)
    subprocess.run([notify, *bot, "--no-voice", text], check=False, cwd=str(HOME), timeout=180)


def log_run(day: date, parts: dict[str, str]) -> None:
    """Append the whole run — every stage — so a reading can be audited later. Append-only,
    like the change log: a correction is a new block, never an edit of an old one."""
    f = state_path("log")
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n===== {day.isoformat()} =====\n")
        for name, body in parts.items():
            fh.write(f"\n--- {name} ---\n{(body or '').strip()}\n")


def save_state(day: date, bio: dict, forecast: dict, computed: str) -> None:
    f = state_path("state")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(
        {"day": day.isoformat(), "biorhythms": computed,
         "bio_conclusion": bio["conclusion"], "summary": forecast["summary"],
         "sent_at": datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="ранковий прогноз: біоритми й астрологія окремо")
    ap.add_argument("--day", help="дата YYYY-MM-DD (типово — сьогодні)")
    ap.add_argument("--subject", help="чия карта (astro.subjects.<name>); типово — власник")
    ap.add_argument("--dry-run", action="store_true", help="весь конвеєр, але нічого не слати й не писати")
    ap.add_argument("--facts", action="store_true", help="тільки пораховані факти, без моделі")
    ap.add_argument("--only", choices=("bio", "astro"), help="тільки одна з двох частин")
    ap.add_argument("--resume", action="store_true",
                    help="переробити лише підсумок із уже записаного черновика й ревʼю")
    ap.add_argument("--show", action="store_true", help="що вже прочитано сьогодні")
    args = ap.parse_args()

    astro.SUBJECT = args.subject
    day = date.fromisoformat(args.day) if args.day else today()
    computed = astro.format_biorhythms(astro.biorhythms(astro.birth_data().date, day))

    if args.show:
        f = path("astro.state")
        print(f.read_text(encoding="utf-8") if f.is_file() else "на сьогодні ще немає")
        return 0

    facts = astro.facts(day)
    if args.facts:
        for f in facts:
            print(f"{f['id']:>14}  {f['text']}"
                  + (f"  [{f['window_text']}]" if f["window_text"] else ""))
        return 0

    note = print if args.dry_run else (lambda *a: None)

    if not args.dry_run and not args.resume and args.only != "bio" and not args.subject:
        # calibrate yesterday before reading today: a rule learned last night has to be in
        # force this morning, not tomorrow
        try:
            from datetime import timedelta
            if mood_feedback.calibrate(day - timedelta(days=1), note):
                note("    калібрування вчорашнього дня враховано")
        except Exception as e:
            note(f"    калібрування не вдалося: {e}")

    if args.resume:                               # one call: redo the summary from the log
        parts = logged_sections(day)
        if not parts.get("черновик"):
            print("у лозі немає черновика на сьогодні", file=sys.stderr)
            return 1
        fixes = split_blocks(parts.get("ревʼю", "")).get("ПРАВКИ", "") or "немає"
        moon = "\n".join(ln for ln in parts.get("факти", "").splitlines()
                          if "Місяць" in ln or ln.startswith("МІСЯЦЬ"))
        answer = fit_budget(summary_call(day, parts.get("факти", ""), moon,
                                         parts["черновик"], fixes, yesterday_block(day)), note)
        blocks = split_blocks(answer)
        forecast = {"main": plain(blocks.get("ГОЛОВНЕ", "")),
                    "lead": plain(blocks.get("КОРОТКО", "")),
                    "summary": plain(blocks.get("ПІДСУМОК", "")),
                    "story": plain(blocks.get("ІСТОРІЯ", "")),
                    "closing": plain(blocks.get("НАСАМКІНЕЦЬ", "")), "raw": answer}
        text = astro_message(day, forecast)
        if args.dry_run:
            print(text)
            return 0
        log_run(day, {"підсумок (перероблено)": answer})
        send(text, note=note)
        return 0

    if args.only == "bio":                        # the biorhythms alone: one call, no ephemeris reading
        bio = write_biorhythms(day, computed)
        text = bio_message(day, bio, computed)
        if args.dry_run:
            print(text)
            return 0
        log_run(day, {"біоритми": bio["raw"]})
        send(text, note=note)
        return 0

    natal = natal_text()
    by_layer = {}
    for f in facts:
        by_layer.setdefault(f.get("layer", "transit"), []).append(f)

    note(f"1/5 транзити поштучно: {len(by_layer.get('transit', []))}")
    read = interpret_facts(natal, day, by_layer.get("transit", []), note)

    note("2/5 шари: доми, Місяць, фон")
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [
            pool.submit(summarise_layer, "ДОМИ", "houses.md", natal, day,
                        by_layer.get("house", []), "ДОМИ", None, note),
            pool.submit(summarise_layer, "МІСЯЦЬ", "moon.md", natal, day,
                        by_layer.get("moon", []), "МІСЯЦЬ",
                        {"НАТАЛЬНИЙ_МІСЯЦЬ": astro.natal_moon_lines()}, note),
            pool.submit(summarise_layer, "ФОН", "background.md", natal, day,
                        by_layer.get("background", []), "ФОН-НЕБА", None, note),
        ]
    layers = [j.result() for j in jobs]
    read = read + [x for x in layers if x]

    note("3/5 зважування")
    # a transient CLI failure here used to throw away all ~14 completed interpretation
    # calls with nothing in the log and no --resume possible (t1051)
    partial = {"факти": fact_lines(read)}
    try:
        rank = weigh(natal, day, read)
        partial["зважування"] = rank["raw"]
        note(f"    основне: {', '.join(rank['main'])}")
        note(f"    чутливе: {', '.join(rank.get('tender', []))}")
        note("4/5 черновик → ревʼю → підсумок")
        forecast = write_forecast(natal, day, read, rank, note, partial)
    except Exception:
        if not args.dry_run:
            log_run(day, partial)
            print("збій на пізній стадії — зроблене записано в лог "
                  f"({', '.join(partial)}); якщо є черновик, допоможе --resume",
                  file=sys.stderr)
        raise
    note("5/5 біоритми")
    bio = ({"figures": "", "conclusion": "", "raw": ""} if args.only == "astro"
           else write_biorhythms(day, computed))

    bio_text, astro_text = bio_message(day, bio, computed), astro_message(day, forecast)

    if args.dry_run:
        print("\n=== ЗВАЖУВАННЯ ===\n" + rank["raw"])
        print("\n=== РЕВʼЮ ===\n" + forecast["review"])
        print("\n=== БІОРИТМИ ===\n" + bio_text)
        print("\n=== АСТРОЛОГІЯ ===\n" + astro_text)
        return 0

    log_run(day, {"факти": fact_lines(read), "зважування": rank["raw"],
                  "черновик": forecast["draft"], "ревʼю": forecast["review"],
                  "підсумок": forecast["raw"], "біоритми": bio["raw"]})
    save_state(day, bio, forecast, computed)
    if args.only != "astro":
        send(bio_text, note=note)
    send(astro_text, note=note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
