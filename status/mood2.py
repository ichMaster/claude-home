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


def items_text(items, ids=None) -> str:
    """The positions as the next stage sees them — compact JSON, one position per line."""
    rows = [i for i in items if ids is None or i["id"] in ids]
    return "\n".join(json.dumps(i, ensure_ascii=False) for i in rows)


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
            previous = out[stage] = call(stage, fill(
                stage, ДАТА=day.isoformat(),
                ВИБРАНЕ=items_text(items, chosen.get("ids")),
                ПОПЕРЕДНЄ=previous,
                БЮДЖЕТ=str(conf2("budget_chars", 1200)),
                МАКСИМУМ=str(conf2("items_max", 5)),
                ГОЛОСНЕ=str(conf2("loud_min", 3))))
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
    mood.send(text, role="mood")


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
        return 4
    except (StageFailed, Unfaithful) as e:
        print(f"v2: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
