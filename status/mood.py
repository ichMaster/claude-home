#!/usr/bin/env python
"""The morning forecast — biorhythms and astrology, as two separate readings.

They are two different things and the owner wants them apart (2026-10-27): biorhythms are
three sine curves from a birth date, astrology is a sky; mixed into one verdict, it stops
being visible which claim came from which. So two messages go out, each with its own voice.

**The astrology half is three calls and is built to be checked** (t1126, 2026-11-01). It
used to be six stages and about seventeen calls, one per transit, producing 3300 characters
in five blocks — and the owner, who listens rather than reads, said it plainly: «те, що
виходить, зовсім не працює і не дає ні прогнозу, ні читабельно». Two separate failures. It
described the day's air, so nothing in it could be checked in the evening or used in the
morning; and it was written for an eye, so in one spoken stream a heading means nothing and
the long middle is where attention goes.

What replaced it:

    facts (local, no model)  →  pick  →  write  →  check

1. `status/astro.py` computes the day: every transit with its window (when it came into orb,
   when it is exact, how long the passage holds), every body standing in a natal house, the
   Moon's aspects **with their clock times**, the retrogrades, the sky's own aspects. No
   model touches a number.
2. **pick** (`mood/pick.md`) — one call: which arc holds for weeks, which two or three
   claims the day can be held to, which action follows. A claim's window must exist in the
   computed facts, so timing is arithmetic rather than invention.
3. **write** (`mood/day.md`) — one call: the four parts, for the ear. ДЕНЬ (one sentence,
   no planets), ПРОГНОЗ (`вікно | що станеться | ознака`), ДІЯ (one line), ДУГА (one
   sentence), and ОСНОВА — the figures, in a block the voice never reads.
4. **check** (`mood/check.md`) — one call that returns the reading *corrected*: every claim
   checkable, every window real, no figure in the spoken parts, the arc matching the
   computed duration, nothing contradicting yesterday in silence.

**The claims are data.** Each is stored in `status/state/forecast-claims.jsonl`; the evening
question (`mood_feedback.py ask`) is built from exactly those, one yes/no each, naming the
window and the sign it was promised by; and `mood_feedback.py score` reports the hit rate.
That is what finally gives the calibration rules a score instead of a pile.

**IMPORTANT** about the headless calls: the Telegram plugin must be off
(`status/digest-settings.json`), or a second session hijacks `getUpdates` and the main one
stops seeing messages. These calls need no connectors, so MCP is stripped too.

    mood.py                 today: compute, read, send both messages
    mood.py --day 2026-10-27
    mood.py --dry-run       the whole pipeline, printed; nothing sent, nothing logged
    mood.py --facts         just the computed facts, no model at all
    mood.py --resume        redo the writing from the pick already in the log
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

# The markers of every stage's answer. ДЕНЬ/ПРОГНОЗ/ДІЯ/ДУГА/ОСНОВА are the sent reading
# since t1126; ДУГА/ПРОГНОЗИ/ВИПРАВЛЕНО belong to the pick and check stages; the rest are
# the biorhythms, the reference and the older stages that still answer in this shape.
_BLOCK_RE = re.compile(r"^[\s*#_>•·—-]*(ЧИТАННЯ|ДЕНЬ|ПРОГНОЗИ|ПРОГНОЗ|ДІЯ|ДУГА|ОСНОВА|ВИПРАВЛЕНО|КОРОТКО|ГОЛОВНЕ|ФАКТИ|ПІДСУМОК|ІСТОРІЯ|НАСАМКІНЕЦЬ|ЧОМУ|ПРАВКИ|ОЦІНКА|ПОКАЗНИКИ|ВИСНОВОК)[\s*_#]*:?[\s*_#]*(.*)$",
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


# The section that holds the reading as it was sent, newest name first. `перевірка` is
# deliberately absent: it stores the raw check output (ОЦІНКА, ПРАВКИ), not the sent text.
# The legacy names stay so days written before t1126 remain readable.
_FINAL_SECTIONS = ("письмо (перероблено)", "письмо",
                   "підсумок (перероблено)", "підсумок", "прогноз")


def final_reading(day: date) -> str:
    """That day's reading as it was sent — the one chain every consumer of the log shares.

    The t1126 rename of the sections silently killed calibration, reference learning and
    yesterday's context, because each parsed the log with its own hardcoded names (t1127).

    Recency is per block, not per name (t1148): a full re-run after a --resume logs a newer
    «письмо», and the stale «письмо (перероблено)» must not outrank what was actually sent
    last — calibration would compare against a reading he never received. Within one block
    the name order still decides, which keeps legacy days readable.
    """
    f = state_path("log")
    if not f.is_file():
        return ""
    text = f.read_text(encoding="utf-8")
    all_marks = list(_LOG_DAY_RE.finditer(text))
    for i in range(len(all_marks) - 1, -1, -1):
        if all_marks[i].group(1) != day.isoformat():
            continue
        end = all_marks[i + 1].start() if i + 1 < len(all_marks) else len(text)
        block = {m.group(1): m.group(2).strip()
                 for m in re.finditer(r"--- (.+?) ---\n(.*?)(?=\n--- |\Z)",
                                      text[all_marks[i].end():end], re.DOTALL)}
        for name in _FINAL_SECTIONS:
            if block.get(name):
                return block[name]
    return ""


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
        final = re.search(
            r"--- (?:письмо(?: \(перероблено\))?|підсумок(?: \(перероблено\))?|прогноз) ---"
            r"(.*?)(?=\n--- |\Z)", block, re.DOTALL)
        body = split_blocks(final.group(1)) if final else {}
        # old format carried the note in ПІДСУМОК; the new one (t1126) in ДЕНЬ/ПРОГНОЗ/ДУГА
        summary = body.get("ПІДСУМОК") or "\n".join(
            p for p in (body.get("ДЕНЬ"), body.get("ПРОГНОЗ"), body.get("ДУГА")) if p)
        if summary:
            return (f"Учорашній прогноз ({last.group(1)}) — щоб не суперечити собі й сказати, "
                    f"якщо лінія триває:\n{summary.strip()[:1200]}")
    return ""


def fact_lines(facts: list[dict]) -> str:
    """The facts as the weighing call reads them: id, the fact, its window, its reading."""
    out = []
    for f in facts:
        window = f" [{f['window_text']}]" if f.get("window_text") else ""
        out.append(f"{f['id']}: {f['text']}{window}\n    {f.get('reading', '')}".rstrip())
    return "\n".join(out)


BLOCKS_SENT = ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА", "ОСНОВА")
SPOKEN_BLOCKS = ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА")       # ОСНОВА is text only
MAX_CLAIMS = 3
CLAIMS = None                                            # set in state_path terms below


# The column names, when a model writes them into the column (t1126: «ознака: відкладеш
# роботу» reached the evening question and was read out).
_LABELS = ("вікно", "що станеться", "що", "ознака", "прогноз")


def _unlabel(part: str) -> str:
    text = part.strip()
    low = text.lower()
    for label in _LABELS:
        if low.startswith(label + ":"):
            return text[len(label) + 1:].strip()
    return text


def claims(text: str) -> tuple[list[dict], int]:
    """The ПРОГНОЗ block as data: `вікно | тема | варіант або варіант або варіант`.

    The third field is a **set of ways the state can show up**, not one sign (the owner,
    2026-11-01: «це дуже однозначно, тому що для кожного вікна може бути декілька
    інтерпретацій»). One aspect does not produce one state: it produces a family, and which
    member of it lands is exactly what the evening can tell us — and the most useful thing
    this project can learn about this chart.

    A line with no window or no theme is dropped and counted. Returns (claims, dropped).
    """
    block = split_blocks(text).get("ПРОГНОЗ", "")
    out, dropped = [], 0
    for line in block.splitlines():
        line = line.strip().lstrip("-•— ").strip()
        if not line:
            continue
        parts = [_unlabel(p) for p in line.split("|")]
        if len(parts) < 3 or not all(parts[:3]):
            dropped += 1
            continue
        variants = [v.strip().strip(",;. ") for v in
                    re.split(r"\s*,?\s+або\s+|\s*;\s*", parts[2]) if v.strip(",;. ")]
        out.append({"window": parts[0], "claim": parts[1], "sign": parts[2],
                    "variants": variants})
    return out[:MAX_CLAIMS], dropped


def claims_file() -> "Path":
    if CLAIMS:
        return CLAIMS
    # per subject, like every other state file (state_path): the claims used to be shared,
    # so a --subject run deleted the owner's rows for the day and the evening question
    # asked him about someone else's states (t1131)
    p = path("astro.claims", "status/state/forecast-claims.jsonl")
    if astro.SUBJECT:
        p = p.with_name(f"{p.stem}-{astro.SUBJECT}{p.suffix}")
    return p


def save_claims(day: date, items: list[dict]) -> None:
    """Store the day's claims, replacing any earlier run of the same day.

    Not append-only, deliberately: a second run of one morning is a correction of the first,
    and the evening question has to ask about what was actually sent.
    """
    f = claims_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    kept = [r for r in _claim_rows(f) if r.get("day") != day.isoformat()]
    for i, item in enumerate(items, 1):
        kept.append({"day": day.isoformat(), "id": f"{day.isoformat()}-{i}",
                     "window": item["window"], "claim": item["claim"],
                     "sign": item["sign"], "variants": item.get("variants", []),
                     # None — not answered; False — nothing of the sort; a string — which of
                     # the variants it actually was, which is what teaches the chart (t1126)
                     "verified": None})
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
                 encoding="utf-8")


def _claim_rows(f: "Path") -> list[dict]:
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_claims(day: date, f=None) -> list[dict]:
    rows = _claim_rows(f or claims_file())
    return [r for r in rows if r.get("day") == day.isoformat()]


def scrub_voice(text: str) -> str:
    """Last safety net for the spoken copy: no degrees, no `dd.mm` dates.

    The prompt forbids them and the review stage checks, but this is cheap and deterministic,
    and a figure read aloud is the thing that made the old reading unlistenable. A clock time
    (`16:00`) is kept — that is what makes a claim checkable.
    """
    out = re.sub(r"\s*\(?\d+[.,]?\d*\s*°\)?", "", text)
    out = re.sub(r"\b(\d{1,2})\.(\d{2})(?!\d)", lambda m: "", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def fit_budget(answer: str, note=lambda *a: None) -> str:
    """One extra call if the result overshoots the length budget.

    The prompt carries per-block limits, but a model that is enjoying itself drifts past
    them, and the owner reads these aloud — «все одно довше виходить» (2026-10-27). Rather
    than truncate mid-sentence, ask once for a cut. Over by a little is left alone; the
    call only pays for itself when the overshoot is real.
    """
    limit = int(conf("astro.budget_chars", 1200))
    blocks = split_blocks(answer)
    size = sum(len(blocks.get(k, "")) for k in SPOKEN_BLOCKS)
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
    if not got.get("ДЕНЬ") and not got.get("ПРОГНОЗ"):
        return answer                             # the cut lost the structure — keep the original
    note(f"    після скорочення: {sum(len(got.get(k, '')) for k in SPOKEN_BLOCKS)} знаків")
    return shorter


def corrected(answer: str) -> str:
    """The check stage's corrected reading, or "" if it did not return one.

    Sliced by hand rather than by `split_blocks`, because the correction **contains** the
    reading's own markers: splitting by marker ended the ВИПРАВЛЕНО block at the ДЕНЬ line
    immediately inside it, so the first live run sent the unchecked draft — with the typo,
    the invented window and the scan edges the editor had just fixed (t1126).
    """
    text = answer or ""
    low = text.upper()
    at = low.find("ВИПРАВЛЕНО")
    if at < 0:
        return ""
    body = text[at + len("ВИПРАВЛЕНО"):]
    end = body.upper().find("ОЦІНКА")
    if end >= 0:
        body = body[:end]
    body = body.strip()
    got = split_blocks(body)
    # a correction that lost the structure is not a correction
    return body if got.get("ДЕНЬ") and got.get("ПРОГНОЗ") else ""


def forecast_parts(answer: str) -> dict[str, str]:
    """The sent reading as its four spoken parts plus the reference."""
    blocks = split_blocks(answer)
    return {"day": plain(blocks.get("ДЕНЬ", "")),
            "claims": plain(blocks.get("ПРОГНОЗ", "")),
            "action": plain(blocks.get("ДІЯ", "")),
            "arc": plain(blocks.get("ДУГА", "")),
            "basis": plain(blocks.get("ОСНОВА", "")),
            "raw": plain(answer)}


def moon_lines(facts: list[dict]) -> str:
    """The day's Moon events with their clock times — where a claim's window comes from."""
    return "\n".join(
        f"  {f['text']}" + (f"  [{f['window_text']}]" if f.get("window_text") else "")
        for f in facts if f.get("layer") == "moon" or f["id"].startswith("m"))


def write_forecast(natal: str, day: date, facts: list[dict], rank: dict | None = None,
                   note=lambda *a: None, partial: dict | None = None,
                   picked: str = "") -> dict[str, str]:
    """Three calls: pick the material, write the reading, check it (t1126).

    The old shape was six stages and about seventeen calls, most of them one per transit —
    and the weighing threw most of those away. What the owner needs is not more material: it
    is two or three claims he can check in the evening, in sixty to ninety seconds. So the
    stages are: **pick** (which arc, which claims, which action — windows taken from the
    ephemeris, never invented), **write** (the four parts, for the ear), **check** (every
    claim has a window and a sign, no figures in the spoken copy, the arc matches the
    computed duration) — and the check returns the corrected text, so there is no fourth call.
    """
    before = yesterday_block(day)
    model = conf("astro.models.final", "")
    budget = str(int(conf("astro.budget_chars", 1200)))

    if picked:
        note("    вибір узято з лога")
    else:
        note("    вибір")
        picked = plain(run_claude(
            fill("pick.md", НАТАЛ=natal, ДАТА=day.isoformat(),
                 ФАКТИ=fact_lines(facts), МІСЯЦЬ=moon_lines(facts),
                 ФОКУС=astro.focus_lines(astro.day_focus(day), day),
                 КОНТЕКСТ=life_context(), КАЛІБРУВАННЯ=calibration(), УЧОРА=before),
            conf("astro.models.judge", "")))
    if partial is not None:
        partial["вибір"] = picked

    note("    письмо")
    written = plain(run_claude(fill("day.md", ДАТА=day.isoformat(), ВИБІР=picked,
                                    ЗНАЧЕННЯ=astro.glossary_lines(),
                                    КОНТЕКСТ=life_context(),
                                    КАЛІБРУВАННЯ=calibration(),
                                    ЕТАЛОН=reference_block(day), БЮДЖЕТ=budget),
                               model))
    if partial is not None:
        partial["письмо"] = written

    note("    перевірка")
    try:
        checked_raw = run_claude(fill("check.md", ДАТА=day.isoformat(), ПРОГНОЗ=written,
                                      ВИБІР=picked, ФАКТИ=fact_lines(facts),
                                      УЧОРА=before, БЮДЖЕТ=budget),
                                 conf("astro.models.review", ""))
        fixed = corrected(checked_raw)
        note(f"    оцінка: {plain(split_blocks(checked_raw).get('ОЦІНКА', ''))[:120]}")
    except Exception as e:                                              # noqa: BLE001
        note(f"    перевірка не вдалася: {e}")
        checked_raw, fixed = "", ""
    # `corrected()` already refuses a correction that lost the structure, so an empty
    # string here means "keep what was written".
    answer = fixed or written
    if partial is not None:
        partial["перевірка"] = checked_raw

    answer = fit_budget(answer, note)
    parts = forecast_parts(answer)
    found, dropped = claims(answer)
    if dropped:
        note(f"    {dropped} прогноз(ів) без вікна або ознаки — відкинуто")
    parts["picked"] = picked
    parts["checked"] = checked_raw
    parts["claim_list"] = found
    parts["dropped"] = dropped
    return parts


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
    """The day, the claims, the action, the arc — then the basis, which is text only.

    Built for the ear (t1126): no spoken headings, and the figures live in one block at the
    end that the voice never reads.
    """
    parts = [f"🜚 Прогноз на {day.strftime('%d.%m')}"]
    if forecast.get("day"):
        parts.append(forecast["day"])
    if forecast.get("claims"):
        parts.append("\n".join(
            "— " + " · ".join(p.strip() for p in line.split("|") if p.strip())
            for line in forecast["claims"].splitlines() if line.strip()))
    if forecast.get("action"):
        parts.append(forecast["action"])
    if forecast.get("arc"):
        parts.append(forecast["arc"])
    if forecast.get("basis"):
        parts.append(f"На чому стоїть\n{forecast['basis']}")
    return "\n\n".join(parts) if len(parts) > 1 else f"{parts[0]}\n\n{plain(forecast['raw'])}"


def spoken(text: str) -> str:
    """What the voice reads: everything but the header line and the reference block.

    «На чому стоїть» is where the degrees and dates live, and a figure read aloud is what
    made the old reading unlistenable (t1126). `scrub_voice` is the net under that.
    """
    body = []
    for part in text.split("\n\n")[1:]:
        if part.startswith(("На чому стоїть", "Пораховано:")):
            continue
        body.append(part)
    return scrub_voice("\n\n".join(body).strip() or text)


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
    """What `/mood` and the `mood` probe show without paying for the reading again.

    `summary` is the probe's one-line answer, so it carries the day's sentence and the
    claims — the two things worth seeing out of context. It used to read
    `forecast["summary"]`, a key of the five-block shape, and the first live run of the new
    pipeline spent four minutes and sent nothing because of it (t1126).
    """
    claims_text = "\n".join(
        f"{c['window']} — {c['claim']}" for c in forecast.get("claim_list", []))
    f = state_path("state")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(
        {"day": day.isoformat(), "biorhythms": computed,
         "bio_conclusion": bio.get("conclusion", ""),
         "summary": "\n\n".join(p for p in (forecast.get("day", ""), claims_text) if p),
         "action": forecast.get("action", ""), "arc": forecast.get("arc", ""),
         "claims": forecast.get("claim_list", []),
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

    if args.resume:                               # redo the writing from the logged pick
        parts = logged_sections(day)
        if not parts.get("вибір"):
            print("у лозі немає вибору на сьогодні", file=sys.stderr)
            return 1
        forecast = write_forecast(natal_text(), day, facts, note=note,
                                  partial=None, picked=parts["вибір"])
        text = astro_message(day, forecast)
        if args.dry_run:
            print(text)
            return 0
        log_run(day, {"письмо (перероблено)": forecast["raw"]})
        save_claims(day, forecast["claim_list"])
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
    note(f"1/3 вибір матеріалу: {len(facts)} фактів")
    partial = {"факти": fact_lines(facts)}
    try:
        forecast = write_forecast(natal, day, facts, note=note, partial=partial)
    except Exception:
        if not args.dry_run:
            log_run(day, partial)
            print("збій на пізній стадії — зроблене записано в лог "
                  f"({', '.join(partial)}); якщо є вибір, допоможе --resume",
                  file=sys.stderr)
        raise
    note("3/3 біоритми")
    bio = ({"figures": "", "conclusion": "", "raw": ""} if args.only == "astro"
           else write_biorhythms(day, computed))

    bio_text, astro_text = bio_message(day, bio, computed), astro_message(day, forecast)

    if args.dry_run:
        print("\n=== ВИБІР ===\n" + forecast["picked"])
        print("\n=== ПЕРЕВІРКА ===\n" + forecast["checked"])
        print("\n=== БІОРИТМИ ===\n" + bio_text)
        print("\n=== ПРОГНОЗ ===\n" + astro_text)
        print(f"\n(прогнозів: {len(forecast['claim_list'])}, "
              f"відкинуто: {forecast['dropped']})")
        return 0

    log_run(day, {"факти": fact_lines(facts), "вибір": forecast["picked"],
                  "письмо": forecast["raw"], "перевірка": forecast["checked"],
                  "біоритми": bio["raw"]})
    save_state(day, bio, forecast, computed)
    save_claims(day, forecast["claim_list"])
    if args.only != "astro":
        send(bio_text, note=note)
    send(astro_text, note=note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
