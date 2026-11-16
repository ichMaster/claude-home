#!/usr/bin/env python
"""The v2 morning reading — the scaffold (t1140, phase 0 of docs/astro-v2-reference.md).

v1 (`status/mood.py`) is not replaced, moved or edited by anything here. It keeps the 08:15
slot until the owner says otherwise, and the two readings are meant to be heard side by side
on the same morning — so v2 has its own entry point, its own prompts, its own log, state and
claims, and nothing on a timer.

Three rules this file exists to enforce, before there is any content to speak of:

* **No fallback.** With no `astro2` block in the configuration the run refuses outright. A
  quiet fallback to v1's paths would let v2 append to v1's history, and that history is the
  record of three rewrites — losing it would cost more than the feature is worth.
* **One ephemeris.** The facts come from `status/astro.py`, the same module and the same call
  v1 uses. A second implementation of the sky would make the two readings incomparable, which
  is the whole point of running them in parallel.
* **No silent prompt.** A missing stage prompt names the file it looked for. An empty string
  passed to the model instead would produce a confident reading of nothing.

The prompts themselves are placeholders until phase 1 (t1143) fills them, and `--send` is
refused while they are, so a scaffold can never deliver a reading made of instructions to
itself.

    status/mood2.py                 run the pipeline for today, print it, log it
    status/mood2.py --day 2026-11-11
    status/mood2.py --dry-run       the whole pipeline, writing nothing and sending nothing
    status/mood2.py --facts         the computed facts only, no model call at all
    status/mood2.py --send          deliver it (refused while the prompts are placeholders)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "status"))
from noosconf import conf, path                                         # noqa: E402

import astro                                                            # noqa: E402
import astro_learn                                                      # noqa: E402
import mood                                                             # noqa: E402

CONFIG_KEY = "astro2"
# A prompt carrying this word is a stub, not an instruction. Phase 1 removes the marker from
# each file as it fills it, so the guard disappears by itself rather than needing a flag.
PLACEHOLDER_MARK = "ЗАГОТОВКА"


class Unconfigured(RuntimeError):
    """No `astro2` block — the one failure that must never degrade into v1's paths."""


class MissingPrompt(RuntimeError):
    """A stage has no prompt file. Named, because an empty prompt fails silently."""


class NotReady(RuntimeError):
    """Asked to send a reading the prompts cannot yet produce."""


class NoCalendar(RuntimeError):
    """No reference day for that date — and phase 1 never fills the gap itself.

    v2 has no sky of its own yet: silence is the honest answer, and it is also what keeps the
    phase measurable. A computed stand-in would look exactly like a read of his calendar.
    """


class Unfaithful(RuntimeError):
    """A stage's answer does not match the source it was given.

    Phase 1's whole contract is fidelity: his calendar is the only sky v2 has, so a stage that
    silently drops a loud window or invents a position is worse than one that fails. Every
    check behind this error is arithmetic — counting markers in his text against the structure
    that came back — so it cannot be talked out of a verdict.
    """


class Undelivered(RuntimeError):
    """The reading was built but Telegram did not take it — notify.sh's exit code is the
    delivery verdict (t1121), and dropping it left the 08:15 timer green while nothing
    arrived (t1172)."""


class StageFailed(RuntimeError):
    """A stage died — timed out or returned non-zero. Named, and never a raw traceback.

    Seen on the first real run of the scaffold (2026-11-11): a placeholder prompt invited the
    model to ramble, the third stage hit the call timeout, and the entry point answered with a
    stack trace ending in `subprocess.TimeoutExpired`. A pipeline that will one day run before
    breakfast has to say which stage stopped and how long it waited.
    """


def require_config() -> dict:
    block = conf(CONFIG_KEY)
    if not isinstance(block, dict) or not block:
        raise Unconfigured(
            f"немає блоку «{CONFIG_KEY}» в конфізі — v2 не запускається. "
            "Це навмисно: без власних шляхів він писав би в історію v1.")
    return block


def conf2(key: str, default=None):
    require_config()
    return conf(f"{CONFIG_KEY}.{key}", default)


def state_path(key: str) -> Path:
    """A v2 state file. Separate from v1's by configuration, not by a suffix bolted on here."""
    require_config()
    p = path(f"{CONFIG_KEY}.{key}")
    if p is None:
        raise Unconfigured(f"у блоці «{CONFIG_KEY}» немає ключа «{key}»")
    return p


def claims_file() -> Path:
    """Where the day's claims will go. The writer arrives with phase 1 (t1143); the path is
    settled now so no stage can be tempted to borrow v1's file."""
    return state_path("claims")


def prompts_dir() -> Path:
    d = Path(str(conf2("prompts", "status/mood2")))
    return d if d.is_absolute() else HOME / d


def stages() -> list[str]:
    names = conf2("stages") or []
    if not names:
        raise Unconfigured(f"у блоці «{CONFIG_KEY}» порожній список «stages»")
    return list(names)


def prompt_text(stage: str) -> str:
    f = prompts_dir() / f"{stage}.md"
    if not f.is_file():
        raise MissingPrompt(f"немає промпта для стадії «{stage}»: {f}")
    return f.read_text(encoding="utf-8")


def placeholders() -> list[str]:
    """Which stages are still stubs. Used by the send guard and worth printing on a run."""
    return [s for s in stages() if PLACEHOLDER_MARK in prompt_text(s)]


def fill(stage: str, **values: str) -> str:
    text = prompt_text(stage)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value or "")
    return text


def fact_text(day: date) -> str:
    """The day's facts, rendered exactly as v1 renders them — one ephemeris, one formatter."""
    return mood.fact_lines(astro.facts(day))


def reference_text(day: date) -> str:
    """His calendar for that date — the only source phase 1 has. Empty string if none."""
    return (astro_learn.for_day(day) or "").strip()


def call(stage: str, prompt: str) -> str:
    models = conf2("models") or {}
    seconds = int(conf2("timeout", mood.CALL_TIMEOUT))
    try:
        return mood.run_claude(prompt, models.get(stage, ""), timeout=seconds)
    except subprocess.TimeoutExpired:
        raise StageFailed(f"стадія «{stage}» не відповіла за {seconds} с") from None
    except RuntimeError as e:
        raise StageFailed(f"стадія «{stage}» не вдалася: {e}") from None


KINDS = {"moon_sign", "moon_house", "void", "ingress", "window", "span", "natal"}
# Only these carry his `✤` marks, so only these are counted against them. A `natal` position
# inherits the weight of the window it hangs under — counting it too would report two loud
# windows where he printed one, which is how the first run of the fidelity check failed.
WEIGHTED = {"window", "span"}


def weight_of(item) -> int:
    """The position's intensity, and zero for anything that is not a plain integer.

    A malformed weight is reported separately by `check_items`; the arithmetic must not raise
    on it on the way there.
    """
    value = item.get("weight", 0)
    return value if isinstance(value, int) and 0 <= value <= 5 else 0


def json_answer(answer: str):
    """The JSON out of a model's reply, fences and chatter tolerated.

    A stage is told to answer with JSON and nothing else; this is the net under that, because
    an occasional «Ось результат:» is not worth a failed run.
    """
    text = (answer or "").strip()
    text = re.sub(r"^```[a-zA-Z]*|```$", "", text, flags=re.MULTILINE).strip()
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        raise Unfaithful("стадія не повернула JSON")
    end = max(text.rfind("]"), text.rfind("}"))
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise Unfaithful(f"JSON не розібрався: {e}") from None


def check_items(items, source: str) -> list[str]:
    """Where the structure disagrees with his text. Counted, not judged.

    Three counts are enough to catch both failure modes that matter. A loud window silently
    dropped would make the reading say the day was quiet; an invented one would put a claim in
    his mouth. The markers are his own: `✤` for intensity, «Холостая Луна» for the gap,
    «Событие влияет» for a hit on the natal chart.
    """
    problems: list[str] = []
    if not isinstance(items, list) or not items:
        return ["порожній або не-масив розбір"]
    # The shape gate first: everything below — and the pick stage after it — assumes dicts
    # keyed by id, so a stray string or an id-less item must fail the parse here, not crash
    # the timer with a raw KeyError three calls later (t1158).
    shapeless = [repr(i)[:80] for i in items
                 if not isinstance(i, dict) or not str(i.get("id") or "").strip()]
    if shapeless:
        return ["позиція без id або не обʼєкт: " + "; ".join(shapeless)]

    ids = [i.get("id") for i in items]
    if len(set(ids)) != len(ids):
        problems.append("однакові id у позиціях")
    for item in items:
        if item.get("kind") not in KINDS:
            problems.append(f"{item.get('id')}: невідомий вид «{item.get('kind')}»")
        if item.get("kind") == "natal":
            # Two natal lines can share one paragraph in his layout — «на мой <планета>(-):▼» and
            # «на мой <планета>(+):▲» followed by one interpretation (seen 15 November). So an
            # empty meaning is legitimate here; what must never be empty is which planet was
            # hit, because that is the claim.
            if not str(item.get("natal", "")).strip():
                problems.append(f"{item.get('id')}: натальна позиція без планети")
        elif not str(item.get("meaning", "")).strip():
            problems.append(f"{item.get('id')}: порожнє трактування")
        if str(item.get("flag", "")) not in ("", "▲", "▼"):
            problems.append(f"{item.get('id')}: невідомий знак «{item.get('flag')}»")
        weight = item.get("weight", 0)
        if not isinstance(weight, int) or not 0 <= weight <= 5:
            problems.append(f"{item.get('id')}: вага «{weight}» поза межами")

    loud_source = source.count("✤✤✤")          # three or more, in his own marks
    loud_items = sum(1 for i in items
                     if i.get("kind") in WEIGHTED and weight_of(i) >= 3)
    if loud_items != loud_source:
        problems.append(f"голосних вікон у тексті {loud_source}, у розборі {loud_items}")

    voids_source = source.count("Холостая Луна") + source.count("Холоста Луна")
    voids_items = sum(1 for i in items if i.get("kind") == "void")
    if voids_items != voids_source:
        problems.append(f"холостої Луни в тексті {voids_source}, у розборі {voids_items}")

    natal_source = source.count("Событие влияет") + source.count("Подія впливає")
    natal_items = sum(1 for i in items if i.get("kind") == "natal")
    if natal_source and natal_items < natal_source:
        problems.append(f"натальних влучань у тексті щонайменше {natal_source}, "
                        f"у розборі {natal_items}")
    elif natal_items and not natal_source:
        # The other direction matters only from zero: one marker may cover several natal
        # lines, but with no marker at all every natal item is an invented claim — and
        # mandatory_ids() would force it into the reading.
        problems.append(f"натальних влучань у тексті нема, у розборі {natal_items}")
    return problems


def blocks(items) -> dict[str, list[dict]]:
    """His own nesting: a `natal` line belongs to the window printed above it.

    In his calendar a hit on the natal chart is not a separate entry — it hangs under the
    window that triggered it, and one window can carry three of them (seen on 15 November).
    Grouping by the nearest preceding weighted
    position reproduces that, which matters twice: the cap on how much a reading says counts
    events rather than lines, and a window can never be spoken without the personal hit it
    carries.
    """
    out: dict[str, list[dict]] = {}
    leader = None
    for item in items:
        if item.get("kind") in WEIGHTED:
            leader = item["id"]
        key = leader if (item.get("kind") == "natal" and leader) else item["id"]
        out.setdefault(key, []).append(item)
    return out


def block_of(item_id: str, items) -> str:
    for key, group in blocks(items).items():
        if any(i["id"] == item_id for i in group):
            return key
    return item_id


def expand(ids, items) -> list[str]:
    """Whole blocks, in the order the day prints them — never half an event."""
    wanted = {block_of(i, items) for i in ids}
    return [i["id"] for key, group in blocks(items).items() if key in wanted for i in group]


def mandatory_ids(items) -> list[str]:
    """What the day cannot be told without: every loud window, every hit on the natal chart.

    Computed here rather than asked of the model: the preferred item count is a preference and
    this is not, so the two must not be able to argue.
    """
    floor = int(conf2("loud_min", 3))
    return [key for key, group in blocks(items).items()
            if any((i.get("kind") in WEIGHTED and weight_of(i) >= floor)
                   or i.get("kind") == "natal" for i in group)]


def pressure(items) -> dict:
    """How heavy the day is, counted rather than judged (t1192).

    His scale runs one to five marks (the owner, 16 November: «максимум це 5»), and the
    intensity he publishes is the one thing in his calendar that says a day has a shape
    instead of being a flat list. A `natal` line inherits the window it hangs under, so a
    window carrying three personal hits is one heavy event and not three.

    `loud` is what may not be dropped; `accent` is what has to be heard loudest.
    """
    floor = int(conf2("loud_min", 3))
    accent_at = int(conf2("accent_min", 4))
    weights = {key: max(weight_of(i) for i in group)
               for key, group in blocks(items).items()}
    return {"top": max(weights.values(), default=0),
            "loud": [k for k, w in weights.items() if w >= floor],
            "accent": [k for k, w in weights.items() if w >= accent_at],
            "weights": weights}


def is_heavy(state: dict) -> bool:
    """A day presses either through one very loud window or through several loud ones."""
    return (bool(state["accent"])
            or len(state["loud"]) >= int(conf2("heavy_blocks", 3)))


def pressure_text(items) -> str:
    """The day's weight in one line, for the writing stage to lean on.

    Deliberately without a single `✤`: the mark is forbidden in everything the voice reads,
    and a glyph put into the prompt is a glyph that can come back out of it — which costs a
    rewrite for nothing. Digits say the same thing.
    """
    state = pressure(items)
    scale = int(conf2("weight_max", 5))
    if not state["loud"]:
        return (f"Доба рівна: голосних позицій немає, найважча важить "
                f"{state['top']} з {scale}. Не роздувай те, чого в добі немає.")
    where = ", ".join(state["accent"] or state["loud"])
    line = (f"Голосних позицій у добі {len(state['loud'])}, найважча важить "
            f"{state['top']} з {scale} — {where}.")
    return line + (" Це важка доба." if is_heavy(state) else "")


def accent_ids(items) -> list[str]:
    """What must be heard loudest: the accented blocks, the loud ones when nothing is louder.

    Empty on a day with nothing weighted at all, and that is the point: `{{НАГОЛОС}}` used to
    be filled with every chosen position, which named the whole day as its own emphasis and so
    said nothing (t1192).
    """
    state = pressure(items)
    return state["accent"] or state["loud"]


def selection(answer, items) -> dict:
    """The model's choice, with the mandatory positions put back and strangers thrown out."""
    picked = answer.get("ids") if isinstance(answer, dict) else None
    known = {i["id"]: i for i in items}
    chosen = [i for i in (picked or []) if i in known]
    unknown = [i for i in (picked or []) if i not in known]
    restored = [i for i in mandatory_ids(items) if block_of(i, items) not in
                {block_of(c, items) for c in chosen}]
    return {"ids": expand(chosen + restored, items),
            "blocks": len({block_of(i, items) for i in expand(chosen + restored, items)}),
            "restored": restored, "unknown": unknown,
            "frame": answer.get("frame") if isinstance(answer, dict) else None,
            "order": answer.get("order", "") if isinstance(answer, dict) else "",
            "drop": answer.get("drop", "") if isinstance(answer, dict) else ""}


def items_text(items, ids=None, label: bool = False) -> str:
    """The positions as the next stage sees them — compact JSON, one position per line.

    With `label`, each position that has a time carries `коли`: the part of the day it falls
    in, computed here so the writing stage never has to work it out (t1153).
    """
    rows = [i for i in items if ids is None or i["id"] in ids]
    if label:
        rows = [dict(i, **({"коли": part_of_day(i.get("from"), i.get("to"))}
                           if part_of_day(i.get("from"), i.get("to")) else {}))
                for i in rows]
    return "\n".join(json.dumps(i, ensure_ascii=False) for i in rows)


# The day in words, because he listens: «мені не важливо з такої-то години — вночі, зранку,
# в обід, після обіду, ввечері» (t1153). The exact hours survive in ОСНОВА, which is read by
# nobody. The label is arithmetic — the part of the day the window spends most of itself in —
# so the writing stage is handed a word instead of being asked to invent one.
PARTS = ((0, 5, "вночі"), (5, 12, "зранку"), (12, 14, "в обід"),
         (14, 18, "після обіду"), (18, 24, "ввечері"))


def _minutes(clock: str):
    try:
        hh, mm = str(clock).split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return None


def part_of_day(frm, to=None) -> str:
    """Which part of the day a window belongs to. Empty when it has no time at all."""
    start = _minutes(frm)
    if start is None:
        return ""
    end = _minutes(to)
    if end is None or end <= start:
        end = start + 1
    best, best_overlap = "", 0
    for h1, h2, name in PARTS:
        overlap = min(end, h2 * 60) - max(start, h1 * 60)
        if overlap > best_overlap:
            best, best_overlap = name, overlap
    return best


# --- the reading, and whether it is his day or a made-up one --------------------------------

MARK = re.compile(r"[ \t]*\[(p\d+(?:[ \t]*,[ \t]*p\d+)*)\]")
SECTIONS = ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ОСНОВА")
CLOCK = re.compile(r"\d{1,2}:\d{2}")
LINE_MAX = 420

# The bodies, as anchored patterns rather than bare substrings (t1177). A stem tested with
# `stem in text` fires inside ordinary words — «уранці» is not Uranus, «лунає» is not the Moon,
# and «вузол напруги» is not Rahu — and each false hit either demands a rewrite for a body
# nobody named or hides a real omission. So each body carries the endings that actually occur
# in his pages and in our readings, with a word boundary at both ends. «Луна» and the Russian
# spellings stay because the read stage translates his pages (t1155).
_ENDINGS = "(?:а|у|ом|і|е)?"
BODY_PATTERNS = {
    "Місяць": r"місяц(?:ь|я|ю|і|е|ем)|лун(?:а|и|ы|е|у|ой|ою)",
    "Меркурій": r"меркурі(?:й|я|ю|ї|єм)|меркури(?:й|я|ю|ем|и)",
    "Венера": r"венер(?:а|и|ы|і|е|у|ою|ой)",
    "Марс": r"марс" + _ENDINGS,
    "Юпітер": r"юп[іи]тер" + _ENDINGS,
    "Сатурн": r"сатурн" + _ENDINGS,
    "Уран": r"уран" + _ENDINGS,
    "Нептун": r"нептун" + _ENDINGS,
    "Плутон": r"плутон" + _ENDINGS,
    "Сонце": r"сонц(?:е|я|ю|ем|і)|солнц(?:е|а|у|ем)",
    "Ліліт": r"л[іи]л[іи]т(?:|и|у|ою|ом|і)",
}

# The nodes are one axis: naming Rahu where his page names Ketu is astrology, not invention.
# But «вузол» is an everyday noun as well as a body, so it answers differently depending on
# which way the check is looking (t1177). Unqualified, it counts as *mentioning* the nodes and
# never as *claiming* them: ambiguous evidence may acquit, never convict.
NODES = "вузли"
NODES_PLAIN = r"раху|кету|узел|узл(?:ы|ов|ам|ами|ах|а|у|ом|е)"
NODES_QUALIFIED = r"(?:місячн|висхідн|низхідн|кармічн)\w*\s+вузл\w*"
NODES_LOOSE = r"вузол|вузл(?:и|ів|ам|ами|ах|а|у|ом|і)"

_WIDE = {**BODY_PATTERNS, NODES: "|".join((NODES_PLAIN, NODES_QUALIFIED, NODES_LOOSE))}
_STRICT = {**BODY_PATTERNS, NODES: "|".join((NODES_PLAIN, NODES_QUALIFIED))}


def _compile(table: dict) -> dict:
    return {name: re.compile(rf"\b(?:{pattern})\b") for name, pattern in table.items()}


WIDE_BODIES = _compile(_WIDE)
STRICT_BODIES = _compile(_STRICT)

SAME_TURN = "це тому, що"


def marked_ids(text: str) -> list[str]:
    """Every position id the reading claims to be built from, in the order it claims them."""
    out: list[str] = []
    for group in MARK.findall(text or ""):
        out.extend(part.strip() for part in group.split(","))
    return out


def strip_marks(text: str) -> str:
    """The reading as a person hears it — the audit markers belong to the log, not the ear."""
    return MARK.sub("", text or "")


def spoken_part(text: str) -> str:
    """Everything before ОСНОВА: the figures are written down, never read out."""
    head = (text or "").split("ОСНОВА")[0]
    return strip_marks(head)


PART_ORDER = ("вночі", "зранку", "в обід", "після обіду", "ввечері", "фоном")


def summary_part(text: str) -> str:
    """The `ДЕНЬ` block alone, markers intact — what he calls «самарі»."""
    return (text or "").split("ДЕНЬ", 1)[-1].split("ПРОГНОЗ", 1)[0]


def forecast_lines(text: str) -> list[str]:
    """The ПРОГНОЗ lines alone, markers stripped."""
    body = (text or "").split("ПРОГНОЗ", 1)[-1].split("ДІЯ", 1)[0]
    return [ln for ln in strip_marks(body).splitlines() if ln.strip()]


def bodies_named(text: str) -> set[str]:
    """Which bodies a piece of text mentions, whatever case the words are in.

    Wide on purpose: used for «did the reading drop something he gave us», where an
    ambiguous word counts in the reading's favour.
    """
    low = (text or "").lower()
    return {name for name, rx in WIDE_BODIES.items() if rx.search(low)}


def bodies_claimed(text: str) -> set[str]:
    """Which bodies a piece of text actually claims — the strict reading (t1177).

    Used for «did the reading invent a body», where an everyday word that merely looks like
    a name must not convict: «вузол напруги» is a knot, not the lunar nodes.
    """
    low = (text or "").lower()
    return {name for name, rx in STRICT_BODIES.items() if rx.search(low)}


def voice_text(text: str) -> str:
    """The spoken copy: no headings, and a breath between the parts of the day (t1157).

    «Тараторить в один суцільний текст і я не встигаю усвідомити» — the reading is two
    thousand characters of dense meaning, and without silence between the parts it arrives as
    one block. The pauses are placed here rather than by a model: where one part of the day
    ends and the next begins is known exactly, and a cheap call that guesses it is worse than
    arithmetic that does not.
    """
    out = []
    for raw in spoken_part(text).splitlines():
        line = raw.strip()
        if not line or line in SECTIONS:
            continue
        if " | " in line:
            when, body = line.split(" | ", 1)
            body = body.replace("; ", ". [пауза] ").replace(" — ", " — [пауза] ", 1)
            out.append(f"[довга пауза] {when}. [пауза] {body}")
        else:
            out.append(f"[довга пауза] {line}")
    return "\n\n".join(out)


def check_reading(text: str, items, chosen_ids=None) -> list[str]:
    """Arithmetic, not judgement: does the reading stand on the positions it was given?

    Three ways it can go wrong, and all three are countable. It can name a position that was
    never in the day (invention). It can quietly drop a loud window or a natal hit, which is
    what turns a heavy day into a calm-sounding one. And it can let a degree into the part the
    voice reads, which is what made v1 unlistenable.
    """
    problems: list[str] = []
    text = text or ""
    for name in SECTIONS:
        if name not in text:
            problems.append(f"нема частини {name}")
    if problems:
        return problems

    order = [text.index(name) for name in SECTIONS]
    if order != sorted(order):
        problems.append("частини йдуть не в тому порядку")

    # The writing stage sees the whole day (t1156), so by default every position is fair
    # game for a marker; a narrower set is only ever passed by a test.
    chosen = set(chosen_ids) if chosen_ids else {i["id"] for i in items}
    used = set(marked_ids(text.split("ОСНОВА")[0]))
    invented = sorted(used - chosen)
    if invented:
        problems.append("позиції, яких у добі немає: " + ", ".join(invented))

    by_id = {i["id"]: i for i in items}
    loud = conf2("loud_min", 3)
    for item_id in sorted(chosen):
        item = by_id.get(item_id)
        if not item:
            continue
        must = weight_of(item) >= loud or item.get("kind") == "natal"
        if must and item_id not in used:
            problems.append(f"{item_id}: голосна позиція не прозвучала")

    # The summary of a heavy day names what makes it heavy (t1192). Checked on the markers
    # rather than on the words, because that is the audit trail the reading already carries —
    # and demanded only where it is cheap to satisfy: the length of the loud line is a prompt
    # rule, since a hard check that can fail every retry buys a silent morning.
    state = pressure(items)
    if state["accent"]:
        named = {block_of(i, items) for i in marked_ids(summary_part(text))}
        if not named & set(state["accent"]):
            problems.append("ДЕНЬ не називає найважчого в добі: "
                            + ", ".join(state["accent"]))

    head = spoken_part(text)
    for bad in ("°", "✤"):
        if bad in head:
            problems.append(f"у тому, що читає голос, є «{bad}» — цифри лише в ОСНОВА")
    if CLOCK.search(head):
        problems.append("у тому, що читає голос, є година — доба називається словами")
    # The cause may be named, but only a cause the day actually carries (t1155).
    # Judged against the whole day, not only the selection: a body the day really carries is
    # at worst a misplaced emphasis, while a silent morning is a failure of the thing itself.
    # The day's side obeys the same asymmetry as the reading's (t1179): `bodies` and `natal`
    # are structured name fields, where a bare «вузли» can only be the nodes — they match
    # wide; `meaning` is his prose, where «вузол» is an everyday noun first — it matches
    # strict. A loose match there both demanded nodes from a nodeless day and excused a
    # reading that complied.
    structured = " ".join(f"{i.get('bodies') or ''} {i.get('natal') or ''}" for i in items)
    prose = " ".join(str(i.get("meaning") or "") for i in items)
    available = bodies_named(structured) | bodies_claimed(prose)
    said = bodies_named(head)
    invented_bodies = sorted(bodies_claimed(head) - available)
    if invented_bodies:
        problems.append("світила, яких у добі немає: " + ", ".join(invented_bodies))
    # And the other direction, which is the one that actually went wrong: he supplies the
    # whole day, so a body that quietly fails to appear is a fact of his thrown away (t1156).
    lost = sorted(available - said)
    if lost:
        problems.append("світила доби, яких у читанні немає: " + ", ".join(lost))
    order_said = [name for name in PART_ORDER
                  if any(line.strip().startswith(name) for line in forecast_lines(text))]
    order_seen = [name for line in forecast_lines(text) for name in PART_ORDER
                  if line.strip().startswith(name)]
    if order_seen != order_said:
        problems.append("частини доби йдуть не по порядку")
    # And it may not be named the same way twice — he asked for prose, not a template.
    if head.lower().count(SAME_TURN) > 1:
        problems.append(f"«{SAME_TURN}» більше одного разу — причина щоразу інакше")
    for line in forecast_lines(text):
        if len(line.strip()) > LINE_MAX:
            problems.append(f"рядок прогнозу довший за {LINE_MAX} знаків")
            break
    return problems


def run(day: date, dry_run: bool = False, note=lambda *a: None) -> dict:
    """The day, stage by stage. Returns stage → what it answered.

    Phase 1 (t1143): his calendar is read into positions, the positions are selected from, and
    the selection is written for the ear. The facts from `status/astro.py` are deliberately not
    consulted — v2 has no sky of its own until phase 3 — so a date he has not covered stops the
    run instead of being quietly computed.
    """
    require_config()
    reference = reference_text(day)
    if not reference:
        raise NoCalendar(f"еталонного календаря на {day.isoformat()} немає — "
                         "доба не придумується")
    out: dict[str, str] = {}
    items: list[dict] = []
    chosen: dict = {}
    previous = ""
    for stage in stages():
        note(f"стадія {stage}")
        if stage == "read":
            items = json_answer(call(stage, fill(
                stage, ДАТА=day.isoformat(), ЕТАЛОН=reference)))
            problems = check_items(items, reference)
            if problems:
                raise Unfaithful("розбір не збігається з еталоном: " + "; ".join(problems))
            previous = out[stage] = items_text(items)
        elif stage == "pick":
            chosen = selection(json_answer(call(stage, fill(
                stage, ДАТА=day.isoformat(), ПОЗИЦІЇ=items_text(items),
                МАКСИМУМ=str(conf2("items_max", 5)),
                ГОЛОСНЕ=str(conf2("loud_min", 3))))), items)
            if chosen["unknown"]:
                note("стадія вибору назвала позиції, яких немає: "
                     + ", ".join(chosen["unknown"]))
            if chosen["restored"]:
                note("обов'язкові позиції повернуто у вибір: "
                     + ", ".join(chosen["restored"]))
            previous = out[stage] = json.dumps(chosen, ensure_ascii=False)
        else:
            base = fill(stage, ДАТА=day.isoformat(),
                        ВИБРАНЕ=items_text(items, label=True),
                        НАГОЛОС=", ".join(accent_ids(items)) or "немає, доба рівна",
                        ТИСК=pressure_text(items),
                        РЯДОК=str(LINE_MAX),
                        ПОПЕРЕДНЄ=previous,
                        БЮДЖЕТ=str(conf2("budget_chars", 1200)),
                        МАКСИМУМ=str(conf2("items_max", 5)),
                        ГОЛОСНЕ=str(conf2("loud_min", 3)))
            final = stage == stages()[-1]
            wrong: list[str] = []
            # The check is arithmetic, so what it found can be handed straight back: a dropped
            # loud window is a fixable mistake, not a reason to leave the morning silent.
            for attempt in range(conf2("retries", 2) + 1):
                previous = call(stage, base if not wrong else
                                base + "\n\n## Що виправити в попередній спробі\n- "
                                + "\n- ".join(wrong)
                                + "\n\nПерепиши читання цілком, не коментуючи правку.")
                if not final:
                    break
                wrong = check_reading(previous, items)
                if not wrong:
                    break
                note(f"читання не пройшло перевірку ({attempt + 1}): " + "; ".join(wrong))
            if final and wrong:
                raise Unfaithful("читання не спирається на добу: " + "; ".join(wrong))
            out[stage] = previous
    if not dry_run:
        log_run(day, out)
        save_state(day, out)
    return out


def log_run(day: date, parts: dict[str, str]) -> None:
    """Append the whole run, like v1's log — a correction is a new block, never an edit."""
    f = state_path("log")
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n===== {day.isoformat()} =====\n")
        for name, body in parts.items():
            fh.write(f"\n--- {name} ---\n{(body or '').strip()}\n")


def save_state(day: date, parts: dict[str, str]) -> None:
    """What a probe or the panel would show without paying for the reading again."""
    f = state_path("state")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(
        {"day": day.isoformat(),
         "stages": parts,
         "reading": parts.get(stages()[-1], ""),
         "placeholders": placeholders(),
         "saved_at": datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=2), encoding="utf-8")


def send(text: str) -> None:
    """Deliver through v1's sender — same bot, same voice profile, so the two are comparable.

    Refused while any stage prompt is a stub: a reading built from placeholder instructions
    would be indistinguishable, to the ear, from a real one.
    """
    stubs = placeholders()
    if stubs:
        raise NotReady("ще заготовки, не промпти: " + ", ".join(stubs)
                       + " — заповнюються у фазі 1 (t1143)")
    # ОСНОВА is the audit trail, not the message: v1 kept it in the text part because it was
    # the only way to trace a claim back to its figure, and he asked for it gone (t1154).
    # It stays in the log and the state, where tracing actually happens.
    if not mood.send(spoken_part(text).strip(), role="mood",
                     voice=voice_text(text), profile=conf2("voice_profile", "zorya-reading")):
        raise Undelivered("notify.sh повернув помилку — читання не дійшло")


def report_failure(text: str) -> None:
    """A --send run that stopped must say so in the chat: the 08:15 timer has no other mouth,
    and nothing watches its exit code — without this the reading just never arrives, with no
    sign why (t1160). Never raises: the real exit code must survive a broken notify."""
    try:
        subprocess.run([str(HOME / "notify.sh"), text],
                       check=False, cwd=str(HOME), timeout=120)
    except Exception:                                                    # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="ранкове читання v2 (каркас, фаза 0)")
    ap.add_argument("--day", help="дата YYYY-MM-DD (типово — сьогодні)")
    ap.add_argument("--dry-run", action="store_true", help="усе показати, нічого не писати")
    ap.add_argument("--facts", action="store_true", help="лише обчислені факти, без моделі")
    ap.add_argument("--send", action="store_true", help="надіслати (поки відмовляє)")
    args = ap.parse_args()

    day = date.fromisoformat(args.day) if args.day else mood.today()
    try:
        require_config()
        if args.facts:
            print(fact_text(day))
            return 0
        parts = run(day, dry_run=args.dry_run, note=lambda m: print(m, file=sys.stderr))
        reading = parts.get(stages()[-1], "")
        print(reading)
        if args.send:
            send(reading)
        stubs = placeholders()
        if stubs:
            print(f"\n(заготовки: {', '.join(stubs)} — фаза 1, t1143)", file=sys.stderr)
    except (Unconfigured, MissingPrompt, NotReady) as e:
        print(f"v2: {e}", file=sys.stderr)
        return 2
    except NoCalendar as e:
        print(f"v2: {e}", file=sys.stderr)
        if args.send:
            report_failure(f"Ранкового читання сьогодні немає: {e}")
        return 4
    except (StageFailed, Unfaithful) as e:
        print(f"v2: {e}", file=sys.stderr)
        if args.send:
            report_failure(f"Ранкове читання не склалось і не надіслане: {e}")
        return 3
    except Undelivered as e:
        print(f"v2: {e}", file=sys.stderr)
        if args.send:
            report_failure(f"Ранкове читання склалось, але не надіслалось: {e}")
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
