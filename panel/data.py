"""What the Pulse screen knows — collectors, kept pure wherever they can be.

The split is deliberate: anything that shells out or touches the clock takes its input as
an argument, so the tests never run `systemctl` and never wait for a probe. `server.py`
does the gathering; this module does the deciding.

The panel has no store of its own (docs/features/ADMIN-PANEL.md § The one hard rule), so
every number here is read from the same file the session reads.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path                                          # noqa: E402

HOME = Path(__file__).resolve().parents[1]
STATE = HOME / "status" / "state"

# severity → the one character the board uses. Colour is earned: grey is normal, amber is
# warn, red is alert, and an unknown severity gets the neutral dot rather than an exception.
MARKS = {"alert": "●", "warn": "●", "info": "·", "quiet": "·"}
CLASSES = {"alert": "alert", "warn": "warn", "info": "ok", "quiet": "quiet"}


# --- probes ---------------------------------------------------------------------------------------------------------

def probe_rows(probes: list[dict], now: datetime | None = None) -> list[dict]:
    """One row per probe: its mark, its one-line answer, and whether the answer is stale.

    Stale means "older than this probe's own TTL" — a board that shows an hour-old outage
    schedule as current is worse than one that shows nothing. An answer carrying no
    timestamp is stale too: unknown age is not freshness.
    """
    now = now or datetime.now(timezone.utc)
    rows = []
    for p in probes:
        sev = str(p.get("severity") or "info")
        ttl = int(p.get("ttl") or 0)
        age = None
        checked = p.get("checked") or p.get("ts")
        if checked:
            try:
                when = datetime.fromisoformat(str(checked))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=now.tzinfo)
                age = max(0, int((now - when).total_seconds()))
            except ValueError:
                age = None
        rows.append({
            "id": p.get("id") or "?",
            "severity": sev,
            "mark": MARKS.get(sev, "·"),
            "css": CLASSES.get(sev, "quiet"),
            "ok": bool(p.get("ok", True)),
            "text": (str(p.get("text") or "").splitlines() or [""])[0],
            "age": age,
            "ttl": ttl,
            "stale": age is None or (ttl > 0 and age > ttl),
        })
    return rows


# --- timers ---------------------------------------------------------------------------------------------------------

def _props(blob: str) -> dict[str, str]:
    """`systemctl show` output — KEY=VALUE lines — as a dict. Machine output, not prose."""
    out = {}
    for line in (blob or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def timer_rows(blobs: list[tuple[str, str, str]]) -> list[dict]:
    """One row per timer from `(unit, timer properties, service properties)`.

    A timer whose service has never run says so instead of crashing, and a property block
    that could not be read yields a row with blanks — on a status board a missing value is
    information, an exception is a blank page.
    """
    rows = []
    for unit, timer_blob, service_blob in blobs:
        t, s = _props(timer_blob), _props(service_blob)
        last = t.get("LastTriggerUSec") or ""
        if not last or last in ("0", "n/a"):
            last, result = "не запускався", ""
        else:
            result = s.get("Result") or ""
        status = s.get("ExecMainStatus")
        # `Result` is the previous run's verdict while the next one is in flight, so a run
        # that is going must not be rendered «успішно» — worst on the eight-minute forecast
        # and the digest (t1114).
        running = (s.get("ActiveState") or "") in ("activating", "active", "reloading",
                                                   "deactivating")
        rows.append({
            "running": running,
            "unit": unit,
            "service": t.get("Unit") or "",
            "next": t.get("NextElapseUSecRealtime") or "",
            "last": last,
            "result": result,
            "failed": bool(result) and result != "success",
            "exit": status if status not in (None, "0") else "",
            "enabled": (t.get("ActiveState") or "") == "active",
        })
    return rows


def timer_units() -> list[str]:
    """The project's own timers, by name. Shells out — and degrades to an empty list when
    systemd does not answer (t1057): one dead collector must not blank the whole page."""
    try:
        out = subprocess.run(["systemctl", "--user", "list-units", "--type=timer", "--all",
                              "--no-legend", "--plain"], capture_output=True, text=True,
                             timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return []
    units = []
    for line in out.stdout.splitlines():
        name = line.split()[0] if line.split() else ""
        if name.startswith(("noos-", "claude-")) and name.endswith(".timer"):
            units.append(name)
    return sorted(units)


def show(unit: str, properties: str) -> str:
    try:
        out = subprocess.run(["systemctl", "--user", "show", unit,
                              f"--property={properties}"],
                             capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return out.stdout


# --- queues ---------------------------------------------------------------------------------------------------------

def _load(f: Path) -> dict:
    """A state file, or {} — a fresh machine has none of these and that is not an error."""
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def queues(state_dir: Path | None = None, now: datetime | None = None) -> dict:
    """The three counters worth watching between runs.

    Two values are deliberately `None` rather than `0` or `""` when there is nothing to say:
    a mailbox whose state file does not exist has an **unknown** last UID, and «UID 0» read
    as a fact about the mailbox (t1114). The YouTube pause is dropped once it has expired —
    it was rendered in amber for the rest of the day.
    """
    d = state_dir or STATE
    now = now or datetime.now(timezone.utc)
    youtube = _load(d / "youtube.json")
    mail = _load(d / "mail.json")
    watch = _load(d / "watch.json")
    loud = sorted(k for k, v in watch.items()
                  if isinstance(v, dict) and v.get("sev") in ("warn", "alert"))
    blocked = str(youtube.get("blocked_until") or "")
    if blocked:
        try:
            until = datetime.fromisoformat(blocked)
            if until.tzinfo is None:
                until = until.replace(tzinfo=now.tzinfo)
            if until <= now:
                blocked = ""
        except ValueError:
            pass                      # an unreadable stamp stays shown, marked as it is
    return {
        "youtube_pending": len(youtube.get("pending") or []),
        "youtube_seen": len(youtube.get("seen") or []),
        "youtube_blocked": blocked,
        "mail_last_uid": mail.get("last_uid") if "last_uid" in mail else None,
        "mail_checked": mail.get("checked") or "",
        "watch_loud": loud,
    }


# --- the change log ---------------------------------------------------------------------------------------------------

def recent_changes(limit: int = 20, log_dir: Path | None = None) -> list[dict]:
    """The newest records across the daily files, newest first.

    The log is append-only and may be written while this reads it, so a torn last line is
    expected and skipped rather than fatal.
    """
    d = log_dir or (HOME / str(conf("changelog.dir", "changelog")))
    if not d.is_dir():
        return []
    rows: list[dict] = []
    for f in sorted(d.glob("*.jsonl"), reverse=True):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue                          # torn tail, or a line being written now
            if len(rows) >= limit:
                return rows
    return rows


def probes_now(ids: list[str] | None = None, cache_dir: Path | None = None) -> list[dict]:
    """Run the probes through the same script the session uses. Shells out.

    A probe's answer carries no timestamp of its own — run.sh keys freshness off the cache
    file's mtime — so each probe is stamped with `checked` from that same mtime here
    (t1056). A probe with no cache file stays unstamped and renders as stale, which is
    right: unknown age is not freshness.
    """
    wanted = ids or list(conf("panel.probes", []) or
                         ["loe", "alarm", "weather", "host", "services", "tasks", "mood"])
    try:
        out = subprocess.run([str(HOME / "status" / "run.sh"), *wanted],
                             capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return []                      # run.sh hung or missing — the board shows the rest
    try:
        probes = json.loads(out.stdout) if out.stdout.strip() else []
    except json.JSONDecodeError:
        return []
    d = cache_dir or (HOME / "status" / "cache")
    for p in probes:
        if p.get("checked") or p.get("ts"):
            continue
        cache = d / (str(p.get("id") or "").replace(":", "-") + ".json")
        try:
            p["checked"] = datetime.fromtimestamp(cache.stat().st_mtime,
                                                  tz=timezone.utc).isoformat()
        except OSError:
            pass
    return probes
