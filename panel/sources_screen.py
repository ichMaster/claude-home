"""Channels, filters and topics — collectors for screen 7.

603 subscriptions, four personal LinkedIn senders and two noise lists: the things that are
painful precisely because they are lists (docs/features/ADMIN-PANEL.md § Why a panel at
all).

Writes go to `config.local.json`, which is git-ignored, holds birth data and the calendar
id, and has no copy anywhere else. Every write therefore goes through the versioned atomic
path (t1080), so a wrong press is one `tools/versions.py restore` away.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import ROOT, atomic_write_text, conf, locked              # noqa: E402

HOME = Path(__file__).resolve().parents[1]
LOCAL = HOME / "config.local.json"


def channels(archive: Path | None = None) -> list[dict]:
    """The polling list, each row with when its last video was seen.

    Activity comes from the subscription archive the probe appends to, so a channel that
    has gone quiet is visible without asking YouTube anything.
    """
    rows = conf("probes.youtube.channels", []) or []
    priority = set(conf("probes.youtube.priority", []) or [])
    last: dict[str, str] = {}
    f = archive or (HOME / "status" / "state" / "youtube-archive.jsonl")
    if f.is_file():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(r, dict):
                continue
            name, when = r.get("channel", ""), (r.get("published") or "")[:10]
            if name and when > last.get(name, ""):
                last[name] = when
    out = []
    for c in rows:
        if not isinstance(c, dict):
            continue
        name = c.get("name") or c.get("handle") or c.get("id") or "?"
        out.append({"name": name, "id": c.get("id", ""), "handle": c.get("handle", ""),
                    "off": bool(c.get("off")), "priority": name in priority,
                    "last": last.get(name, "")})
    return out


def sort_channels(rows: list[dict], order: str = "activity") -> list[dict]:
    """`activity` — the quiet ones last, which is what makes a dead channel findable."""
    if order == "name":
        return sorted(rows, key=lambda c: c["name"].lower())
    return sorted(rows, key=lambda c: (c["last"] or "", c["name"].lower()), reverse=True)


def _mail_defaults() -> dict:
    """The mail probe's own seed lists: the probe starts from DEFAULT_RULES and merges the
    rules file over them, so a screen that starts from empty lists answers the opposite of
    what the probe does whenever the file is absent or partial (t1086)."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            "noos_mail_probe", HOME / "status" / "probes" / "mail.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {k: list(v) for k, v in mod.DEFAULT_RULES.items()}
    except Exception:                                                    # noqa: BLE001
        return {"шум": [], "важливе": []}


MAIL_DEFAULTS = _mail_defaults()


def filters() -> dict:
    """The mail and social filters, as the probes read them."""
    rules = HOME / "status" / "mail-rules.json"
    mail = {k: list(v) for k, v in MAIL_DEFAULTS.items()}
    if rules.is_file():
        try:
            got = json.loads(rules.read_text(encoding="utf-8", errors="replace"))
            if isinstance(got, dict):
                mail = {**mail, **got}
        except json.JSONDecodeError:
            pass
    return {
        "mail": mail,
        "linkedin_personal": conf("probes.linkedin.personal_senders", []) or [],
        "linkedin_noise": conf("probes.linkedin.noise_senders", []) or [],
        "facebook": conf("probes.facebook.senders", []) or [],
    }


def classify(sender: str, subject: str, rules: dict) -> str:
    """What the mail probe would call this message — the same two lists, same order.

    A test box rather than a live IMAP run: it answers instantly, costs nothing, and the
    question being asked is almost always "would this one have been filtered", not "what
    came in the last day".
    """
    blob = f"{sender} {subject}".lower()
    noise = [s for s in (rules.get("шум") or []) if s and s.lower() in blob]
    important = [s for s in (rules.get("важливе") or []) if s and s.lower() in blob]
    if important:
        return f"важливе (збіг: {', '.join(important)})"
    if noise:
        return f"шум (збіг: {', '.join(noise)})"
    return "звичайне"


# --- writes --------------------------------------------------------------------------------

def _load_local() -> dict:
    if not LOCAL.is_file():
        return {}
    try:
        got = json.loads(LOCAL.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"config.local.json не читається: {exc}") from exc
    return got if isinstance(got, dict) else {}


def _save_local(data: dict) -> None:
    atomic_write_text(LOCAL, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def set_channel(name: str, *, off: bool | None = None,
                priority: bool | None = None) -> str:
    """Disable a channel or star it. Writes the personal config through the versioned path.

    The whole read-modify-write is under the file's lock: four writers share this file and
    without it the last reader wins, dropping the other's change (t1104).
    """
    with locked(LOCAL):
        return _set_channel_locked(name, off=off, priority=priority)


def _set_channel_locked(name: str, *, off: bool | None = None,
                        priority: bool | None = None) -> str:
    data = _load_local()
    yt = data.setdefault("probes", {}).setdefault("youtube", {})
    rows = yt.setdefault("channels", [])
    found = next((c for c in rows if isinstance(c, dict)
                  and (c.get("name") or c.get("handle") or c.get("id")) == name), None)
    if found is None:
        return f"каналу «{name}» у списку немає"
    said = []
    if off is not None:
        found["off"] = bool(off)
        said.append("вимкнено" if off else "увімкнено")
    if priority is not None:
        stars = yt.setdefault("priority", list(conf("probes.youtube.priority", []) or []))
        if priority and name not in stars:
            stars.append(name)
        if not priority and name in stars:
            stars.remove(name)
        said.append("у пріоритеті" if priority else "без пріоритету")
    _save_local(data)
    return f"{name}: {', '.join(said)}"
