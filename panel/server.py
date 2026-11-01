#!/usr/bin/env python
"""The admin panel — phase 1: the shell and the Pulse screen.

    panel/server.py [--port 8091] [--once]

Binds what `panel.host` says — `0.0.0.0` since 2026-10-31, by the owner's choice, because he
works from another machine on the same network. That made the original reasoning obsolete
("no authentication and there must not be one: a login form on a loopback socket reached
through an SSH tunnel is decoration"), and phase 8's review showed what an open port means in
practice. So since t1100 there is a login: one shared password, hashed into `.env.panel` and
set from a terminal, a session in memory, five attempts per address. `panel/auth.py`.

Read-only still, by phase: the screens that write (configuration, permissions, timer times)
wait for phase 10, now that phase 11 has given the panel a way to tell who is asking.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import secrets
import subprocess
import sys
import time
import traceback
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "panel"))

from noosconf import atomic_write_text, conf                            # noqa: E402
import bruno                                                           # noqa: E402
import changes                                                         # noqa: E402
import data                                                            # noqa: E402
import memory_screen                                                   # noqa: E402
import auth                                                            # noqa: E402
import prompt_screen                                                   # noqa: E402
import render                                                          # noqa: E402
import rules_screen                                                    # noqa: E402
import sources_screen                                                  # noqa: E402
import tasks_screen                                                    # noqa: E402
import zirka                                                           # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
# Where this user's systemd units live. The schedule editor writes here and nowhere else,
# and only to a unit systemd itself named (t1103).
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
# screen → the phase that builds it, for the placeholder pages
SOON = {
    "/chat": "фаза 9",
}
TITLES = dict(render.SCREENS)


def pulse_html() -> str:
    """Gather, then hand everything to the pure renderers."""
    probes = data.probe_rows(data.probes_now())
    timers = data.timer_rows([
        (u,
         data.show(u, "Unit,NextElapseUSecRealtime,LastTriggerUSec,ActiveState"),
         data.show(u.replace(".timer", ".service"), "Result,ExecMainStatus,ActiveState"))
        for u in data.timer_units()])
    return render.render_pulse(probes, timers, data.queues(),
                               data.recent_changes(int(conf("panel.changes", 20))),
                               int(conf("panel.refresh_sec", 30)))


def changes_html(query: str = "") -> str:
    """Screen 10. The git calls live here; the parsing they feed is pure and tested."""
    ahead = changes.ahead_hashes()                    # None = origin unreachable, say so
    rows = changes.commit_rows(
        changes.git("log", f"--format={changes.LOG_FORMAT}",
                    f"-{int(conf('panel.commits', 40))}"),
        ahead)
    tasks = {}
    try:
        # Appended, not inserted, and only once: this runs per request in a 24/7 process,
        # and the task-title import is a nicety that must not outrank the panel's modules.
        tasks_dir = str(HOME / "tasks")
        if tasks_dir not in sys.path:
            sys.path.append(tasks_dir)
        from store import state as task_state                           # noqa: E402
        tasks = task_state()
    except Exception:                                                   # noqa: BLE001
        pass                                                            # titles are a nicety
    details = {r["sha"]: changes.commit_detail(r, tasks) for r in rows}
    nights = changes.review_nights()
    # A query searches weeks of the log, not the display window: one day already produces
    # hundreds of records, and a miss over a truncated window reads as "never happened".
    limit = int(conf("panel.changes_search", 5000)) if query else \
        int(conf("panel.changes_full", 200))
    log = changes.filter_changes(data.recent_changes(limit), query)
    return render.render_changes(rows, details, nights, changes.open_lows(nights),
                                 len(ahead) if ahead is not None else None,
                                 log[:60], query)


# --- authentication (t1100) ---------------------------------------------------------------
# One password, one person. Sessions live here and nowhere else: a restart logs out, and the
# panel gains no second secret on disk to protect. The failure mode of this whole mechanism
# is a lockout rather than a leak, so the escape hatch is `panel/auth.py clear` in a
# terminal — the one place that proves who is asking.
SESSIONS: dict[str, float] = {}          # token -> expiry, unix seconds
ATTEMPTS: dict[str, dict] = {}           # source address -> {fails, until}
AUTH_LOG = HOME / "status" / "state" / "panel-auth.jsonl"
COOKIE = "noos_panel"


def configured() -> bool:
    """Is a password set? No password means the panel serves only the login page — an
    unconfigured panel must never read as an open one."""
    return bool(auth.stored_record())


def new_session() -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time() + float(conf("panel.auth.ttl_hours", 12)) * 3600
    for old_token, expiry in list(SESSIONS.items()):          # cheap housekeeping
        if expiry < time.time():
            SESSIONS.pop(old_token, None)
    return token


def valid_session(token: str) -> bool:
    if not token:
        return False
    for known, expiry in SESSIONS.items():
        if secrets.compare_digest(known, token):
            return expiry > time.time()
    return False


def drop_session(token: str) -> None:
    SESSIONS.pop(token, None)


def cookie_header(token: str, ttl_hours: float | None = None) -> str:
    """HttpOnly so a script cannot read it, SameSite=Strict so another origin cannot ride
    it, Path=/ so one login covers the whole panel. No `Secure`: there is no TLS here, and
    marking it secure over plain HTTP would simply stop the cookie from being sent."""
    hours = float(ttl_hours if ttl_hours is not None else conf("panel.auth.ttl_hours", 12))
    return (f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; "
            f"Max-Age={int(hours * 3600)}")


def cookie_token(header: str | None) -> str:
    for part in (header or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name == COOKIE:
            return value.strip()
    return ""


def open_path(path: str) -> bool:
    """The only two things served without a session: the login page and the stylesheet.

    `/static/` is matched on a cleaned path, so `/static/../.env.voice` is not "open" —
    `static_file()` would refuse it anyway, but a path that walks out of its directory has
    no business being judged by its prefix.
    """
    if path == "/login":
        return True
    return path.startswith("/static/") and ".." not in path


def _log_attempt(source: str, result: str) -> None:
    """Every attempt, with its outcome and never the password tried. The log is the point
    as much as the lock: an attempt from an address that is not his should be visible."""
    try:
        AUTH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUTH_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                                "from": source, "result": result},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass                      # a login must not fail because the log is unwritable


def try_login(password: str, source: str) -> str | None:
    """A token on success, None otherwise. Rate-limited per source address, because a
    password on a local network without a limit is a dictionary and five minutes."""
    limit = int(conf("panel.auth.max_attempts", 5))
    lock_s = float(conf("panel.auth.lock_min", 5)) * 60
    state = ATTEMPTS.setdefault(source, {"fails": 0, "until": 0.0})
    if state["until"] > time.time():
        _log_attempt(source, "locked")
        return None
    if not configured() or not auth.check_password(password, auth.stored_record()):
        state["fails"] += 1
        if state["fails"] >= limit:
            state["until"] = time.time() + lock_s
            state["fails"] = 0
            _log_attempt(source, "locked")
        else:
            _log_attempt(source, "fail")
        return None
    state["fails"], state["until"] = 0, 0.0
    _log_attempt(source, "ok")
    return new_session()


# Minted once per process and required on every POST. This is not authentication and does
# not pretend to be: it stops a page on some other origin — anything the owner opens while
# on this network — from driving the panel, which matters precisely because there is no
# login and these buttons start eight-minute pipelines (t1068).
FORM_TOKEN = secrets.token_urlsafe(24)


def check_token(value: str) -> bool:
    return bool(value) and secrets.compare_digest(value, FORM_TOKEN)


def host_ok(header: str | None) -> bool:
    """Reject a Host naming a DNS domain — the one thing DNS rebinding cannot fake away.

    The token stops a cross-origin page from posting here; rebinding makes the attacker's
    page *same-origin* (their domain re-resolves to this panel's address), after which the
    token can be read out of the page and replayed. Every such request still carries the
    attacker's own domain in Host. The owner reaches the panel by IP, `localhost` or a
    tailnet name, so that is all that is accepted; extra names go in `panel.hosts` (t1069).
    A missing Host is let through — only non-browser clients omit it, and rebinding needs
    a browser.
    """
    if not header:
        return True
    host = header.strip()
    if host.startswith("["):                                 # [::1]:8091
        host = host[1:host.find("]")] if "]" in host else host[1:]
    else:
        host = host.rsplit(":", 1)[0]
    if host == "localhost" or host.endswith(".ts.net"):
        return True
    if host in (conf("panel.hosts", []) or []):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def run_script(*cmd: str, timeout: int = 300, cap: int = 600,
               tail: bool = False) -> tuple[bool, str]:
    """Run one of the project's own scripts. A failure is returned, never swallowed.

    `cap` and `tail` belong to the caller, because a task message and a journal page want
    opposite ends of the same string: a message rides a redirect query string and wants its
    first 600 characters, a journal wants its last lines (t1096). A cut tail says so.
    """
    try:
        out = subprocess.run(list(cmd), capture_output=True, text=True,
                             timeout=timeout, cwd=str(HOME))
    except (OSError, subprocess.SubprocessError) as exc:
        # OSError too: execve raises it directly — E2BIG on an oversized argument, a
        # missing interpreter — and uncaught it became the handler's bare 500 (t1079)
        return False, f"не вдалося запустити: {exc}"
    ok = out.returncode == 0
    said = (out.stdout or "").strip() or (out.stderr or "").strip()
    if cap and len(said) > cap:
        said = ("… обрізано\n" + said[-cap:]) if tail else said[:cap]
    return ok, said


def save_reference(text: str, day: str, author: str, learn: bool) -> str:
    """Store a pasted reference and hand it to `astro_learn.py`.

    The text is written to the same inbox Zirka's chat parks into, so there is one place
    where references live whichever door they came through, and the script reads it with
    `--file` — a few thousand characters have no business on a command line.
    """
    if not text.strip():
        return "Порожній текст — нічого зберігати."
    try:
        when = date.fromisoformat(day) if day else date.today()
    except ValueError:
        return f"Не зрозумів дату «{day}»."
    folder = HOME / "status" / "state" / "astro-reference-inbox"
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{when.isoformat()}.txt"
    f.write_text(text, encoding="utf-8")

    cmd = [str(HOME / ".venv-voice" / "bin" / "python"),
           str(HOME / "status" / "astro_learn.py"), "add", "--file", str(f),
           "--day", when.isoformat(), "--period", "день"]
    if author.strip():
        cmd += ["--author", author.strip()]
    if learn:
        cmd.append("--learn")
    ok, said = run_script(*cmd, timeout=900)
    if not ok:
        return f"Текст збережено у {f.name}, але внести не вдалося: {said}"
    return f"Еталон записано ({len(text)} символів, на {when.isoformat()}). {said}"


def static_file(path: str) -> tuple[bytes, str] | None:
    """Serve one file out of `panel/static`, or nothing.

    `resolve()` plus the parent check is what stops `/static/../../.env.voice`: the panel
    has no authentication, so path traversal here would hand out the keys.
    """
    target = (STATIC / path.lstrip("/")).resolve()
    if STATIC.resolve() not in target.parents or not target.is_file():
        return None
    kind = {"css": "text/css; charset=utf-8", "js": "text/javascript; charset=utf-8",
            "svg": "image/svg+xml"}.get(target.suffix.lstrip("."),
                                        "application/octet-stream")
    return target.read_bytes(), kind


def bruno_html(query: str = "") -> str:
    """Screen 5. Read-only: phase 4 adds no button, because nothing here needs pressing
    yet and an action on this screen can wait for a reason to exist."""
    return render.render_bruno(
        news=bruno.sent_news(), videos=bruno.sent_videos(),
        dropped=bruno.dropped_news(), stats=bruno.archive_stats(),
        found=bruno.archive_search(query), query=query,
        chat=bruno.bruno_chat(), topics=bruno.topics(), prompts=bruno.prompts())


def task_state() -> dict:
    """The task log, through store.py — one reader, one validator. Appended to sys.path
    once, never per request (the leak t1067 and t1071 were both about)."""
    d = str(HOME / "tasks")
    if d not in sys.path:
        sys.path.append(d)
    from store import state                                             # noqa: E402
    return state()


def tasks_html(message: str = "") -> str:
    """Screen 9."""
    try:
        cols = tasks_screen.columns(task_state())
    except Exception as exc:                                            # noqa: BLE001
        cols = {"today": [], "period": [], "backlog": [], "closed": []}
        message = (message + f" Журнал задач не прочитався: {exc}").strip()
    return render.render_tasks(cols, FORM_TOKEN, message)


def tasks_action(form: dict) -> str:
    """One button → one `store.py` verb. The log stays append-only and its validation
    stays in the one place that already has it."""
    what = (form.get("action") or [""])[0]
    tid = (form.get("id") or [""])[0].strip()
    py = str(HOME / ".venv-voice" / "bin" / "python")
    store = str(HOME / "tasks" / "store.py")

    if what == "add":
        text = (form.get("text") or [""])[0].strip()
        if not text:
            return "Порожній рядок — задачу не додано."
        ok, said = run_script(py, store, "add", text, timeout=60)
        return said if ok else f"Не вдалося додати: {said}"
    if what in ("done", "start", "stop", "cancel"):
        if not tid:
            return "Задачу не названо."
        ok, said = run_script(py, store, what, tid, timeout=60)
        return said if ok else f"Не вдалося: {said}"
    if what == "defer":
        when = (form.get("when") or [""])[0].strip()
        if not tid or not when:
            return "Задачу або дату не названо."
        ok, said = run_script(py, store, "defer", tid, when, timeout=60)
        return said if ok else f"Не вдалося перенести: {said}"
    if what == "block":
        on = (form.get("on") or ["on"])[0]
        if not tid:
            return "Задачу не названо."
        ok, said = run_script(py, store, "block", tid, on, timeout=60)
        return said if ok else f"Не вдалося: {said}"
    return "Невідома дія."


def memory_html(query: str = "", message: str = "") -> str:
    """Screen 6."""
    return render.render_memory(memory_screen.facts(), memory_screen.archive(),
                                memory_screen.search(query), query, FORM_TOKEN, message)


def memory_action(form: dict) -> str:
    """Facts change through facts.py, which is also what builds the prompt — one writer,
    one format. Deleting takes a version first (t1080), so a wrong press is recoverable."""
    what = (form.get("action") or [""])[0]
    fid = (form.get("id") or [""])[0].strip()
    py = str(HOME / ".venv-voice" / "bin" / "python")
    facts_py = str(HOME / "memory" / "facts.py")

    if what == "add":
        text = (form.get("text") or [""])[0].strip()
        if not text:
            return "Порожній факт — нічого додавати."
        pin = (form.get("pin") or ["1"])[0].strip() or "1"
        if pin not in ("0", "1", "2"):
            return "Рівень закріплення буває 0, 1 або 2."
        ok, said = run_script(py, facts_py, "add", "--pin", pin, text, timeout=60)
        return said if ok else f"Не вдалося додати: {said}"
    if not fid:
        return "Факт не названо."
    if what == "rm":
        ok, said = run_script(py, facts_py, "rm", fid, timeout=60)
        return (said + " — повернути можна через tools/versions.py restore") if ok \
            else f"Не вдалося видалити: {said}"
    if what in ("pin_up", "pin_down"):
        rows = memory_screen.facts()
        current = next((f for f in rows["in_prompt"] + rows["cut"] + rows["unpinned"]
                        if f["id"] == fid), None)
        if not current:
            return "Такого факту немає."
        # the prompt ranks ascending — pin 1 is critical and first, 2 fits if room is
        # left, 0 never enters — so «вище» walks 0→2→1, not +1 (t1084: +1 demoted a
        # pin-1 fact and on a pin-2 fact clamped into doing nothing at all)
        pin = current["pin"] if current["pin"] in (0, 1, 2) else 1
        level = ({0: 2, 2: 1, 1: 1} if what == "pin_up" else {1: 2, 2: 0, 0: 0})[pin]
        ok, said = run_script(py, facts_py, "pin", fid, str(level), timeout=60)
        return said if ok else f"Не вдалося змінити рівень: {said}"
    return "Невідома дія."


def sources_html(query: str = "", order: str = "activity", message: str = "",
                 probe: str = "") -> str:
    """Screen 7."""
    rows = sources_screen.channels()
    if query:
        needle = query.lower()
        rows = [c for c in rows if needle in c["name"].lower()]
    rows = sources_screen.sort_channels(rows, order)
    total = len(rows)
    return render.render_sources(rows[:int(conf("panel.channels_shown", 200))],
                                 sources_screen.filters(), bruno.topics(), probe,
                                 FORM_TOKEN, message, query, order, total)


def sources_action(form: dict) -> tuple[str, str]:
    """Returns (message, probe) — the probe is the filter test's answer, which is not a
    change and so does not belong in the same line as one."""
    what = (form.get("action") or [""])[0]
    name = (form.get("name") or [""])[0]
    if what == "test":
        got = sources_screen.classify((form.get("sender") or [""])[0],
                                      (form.get("subject") or [""])[0],
                                      sources_screen.filters()["mail"])
        return "", f"Цей лист пройшов би як: {got}"
    if what not in ("off", "priority"):
        return "Невідома дія.", ""
    if not name:
        return "Канал не названо.", ""
    try:
        if what == "off":
            said = sources_screen.set_channel(
                name, off=(form.get("off") or ["1"])[0] == "1")
        else:
            said = sources_screen.set_channel(
                name, priority=(form.get("priority") or ["1"])[0] == "1")
    except RuntimeError as exc:
        return str(exc), ""
    return said, ""


def zirka_html(day: str = "", message: str = "") -> str:
    """Screen 4. Reading from disk happens here; the parsing it feeds is pure and tested."""
    try:
        when = date.fromisoformat(day) if day else zirka.today()
    except ValueError:
        when = zirka.today()
    log = zirka.log_text()
    runs = zirka.day_runs(log, when)
    summary = runs[0]["summary"] if runs else ""
    own, ref = zirka.rules_text()
    try:
        # Appended, not inserted, and only once: this runs per request in a 24/7 process
        # (the same guard changes_html carries, t1067).
        status_dir = str(HOME / "status")
        if status_dir not in sys.path:
            sys.path.append(status_dir)
        import astro                                                    # noqa: E402
        facts = [f["text"] + (f"  [{f['window_text']}]" if f.get("window_text") else "")
                 for f in astro.facts(when)]
    except Exception as exc:                                            # noqa: BLE001
        facts = [f"факти не порахувались: {exc}"]
    return render.render_zirka(
        day=when.isoformat(), blocks=zirka.reading_blocks(summary), runs=runs,
        facts=facts, own_rules=own, ref_rules=ref, feedback=zirka.feedback(),
        refs=zirka.references(), parked=zirka.parked(), token=FORM_TOKEN,
        message=message)


def zirka_action(form: dict) -> str:
    """One POST → one action, each a call to a script that already exists."""
    what = (form.get("action") or [""])[0]
    day = (form.get("day") or [""])[0] or zirka.today().isoformat()
    py = str(HOME / ".venv-voice" / "bin" / "python")

    if what == "reference":
        return save_reference((form.get("text") or [""])[0], day,
                              (form.get("author") or [""])[0],
                              bool(form.get("learn")))
    if what == "ingest":
        name = (form.get("file") or [""])[0]
        folder = HOME / "status" / "state" / "astro-reference-inbox"
        f = (folder / name).resolve()
        # the name comes from a form field, so it is not trusted to stay in its folder
        if folder.resolve() not in f.parents or not f.is_file():
            return "Такого файлу немає."
        ok, said = run_script(py, str(HOME / "status" / "astro_learn.py"), "add",
                              "--file", str(f), "--day", f.stem.split("-", 2)[-1],
                              "--period", "день", "--learn", timeout=900)
        return (f"Внесено: {said}" if ok else f"Внести не вдалося: {said}")
    if what == "recalc":
        unit = str(conf("astro.recalc_unit", "noos-mood-recalc"))
        ok, said = run_script("systemd-run", "--user", f"--unit={unit}", "--collect",
                              "--setenv", f"HOME={HOME.parent}", py,
                              str(HOME / "status" / "mood.py"), "--day", day, timeout=60)
        if not ok and "exists" in said:
            return "Перерахунок уже йде."
        return ("Перерахунок запущено — читання прийде в чат Зірки хвилин за вісім."
                if ok else f"Не запустилось: {said}")
    if what == "ask":
        ok, said = run_script(py, str(HOME / "status" / "mood_feedback.py"), "ask",
                              "--force", timeout=300)
        return "Питання надіслано." if ok else f"Не вдалося: {said}"
    if what == "calibrate":
        ok, said = run_script(py, str(HOME / "status" / "mood_feedback.py"), "calibrate",
                              "--day", day, timeout=600)
        return (f"Калібрування за {day}: {said}" if ok else f"Не вдалося: {said}")
    return "Невідома дія."


def session_started() -> float:
    """When the live session started, from its own systemd unit — the moment it read
    `persona.md`, `CLAUDE.md` and the facts. Unknown start time means no banner rather than
    a false one (t1101)."""
    out = data.show(str(conf("panel.session_unit", "claude-home.service")),
                    "ExecMainStartTimestamp")
    stamp = (out or "").partition("=")[2].strip()
    for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%a %Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(stamp, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def dirty_files() -> set[str]:
    """Which tracked files have uncommitted changes — `git status`, not a guess."""
    ok, said = run_script("git", "status", "--porcelain", timeout=20)
    if not ok:
        return set()
    return {Path(line[3:].strip()).name for line in said.splitlines() if line.strip()}


def prompt_html(message: str = "") -> str:
    """Screen 2. The prompt is rebuilt exactly as `start.sh` builds it, from the same files
    and the same `facts.py prompt`, so what is shown is what the session was told."""
    try:
        persona = (HOME / "persona.md").read_text(encoding="utf-8")
    except OSError as exc:
        persona, message = "", f"{message} persona.md не прочитався: {exc}".strip()
    ok, facts = run_script(str(HOME / ".venv-voice" / "bin" / "python"),
                           str(HOME / "memory" / "facts.py"), "prompt",
                           timeout=60, cap=40000)
    handoff = None
    note = HOME / "memory" / "handoff.md"
    if note.is_file():
        try:
            handoff = note.read_text(encoding="utf-8")
        except OSError:
            handoff = None
    perms = ""
    try:
        sys.path.append(str(HOME / "tools"))
        import permissions as perm_tool                                 # noqa: E402
        perms = perm_tool.prompt_block()
    except Exception:                                                   # noqa: BLE001
        perms = ""                      # a missing block is visible as a missing part
    got = prompt_screen.assembled(persona, facts if ok else "", handoff,
                                  permissions=perms)
    started = session_started()
    watched = [HOME / "persona.md", HOME / "CLAUDE.md",
               *sorted((HOME / "memory" / "facts").glob("*.md"))]
    stale = prompt_screen.stale_files(started, watched) if started else []
    files = prompt_screen.prompt_files([HOME / "persona.md", HOME / "CLAUDE.md"],
                                       dirty_files())
    if not ok:
        message = (message + " факти не зібрались: " + facts).strip()
    return render.render_prompt(got, stale, files, message, token=FORM_TOKEN)


def scenarios_html(message: str = "") -> str:
    """Screen 3."""
    items = prompt_screen.scenarios()
    units = {str(i.get("unit")) for i in items if i.get("unit")}
    timers = {}
    for unit in sorted(units):
        rows = rules_screen.schedule_rows([(
            unit,
            data.show(unit, "Unit,Description,TimersCalendar,TimersMonotonic,"
                            "NextElapseUSecRealtime,NextElapseUSecMonotonic,"
                            "LastTriggerUSec,ActiveState"),
            data.show(unit.replace(".timer", ".service"),
                      "Result,ExecMainStatus,ActiveState"))],
            boot_epoch=_boot_epoch())
        timers[unit] = rows[0]
    return render.render_scenarios(prompt_screen.scenario_rows(items, timers),
                                   FORM_TOKEN, message)


def prompt_action(form: dict) -> str:
    """Screen 2's writes (t1103): `persona.md` and `CLAUDE.md`, by name, nothing else."""
    if (form.get("action") or [""])[0] != "save":
        return "Невідома дія."
    ok, said = prompt_screen.save_file((form.get("file") or [""])[0],
                                       (form.get("text") or [""])[0],
                                       confirm=bool(form.get("confirm")))
    return said if ok else f"Не збережено: {said}"


def scenario_action(form: dict) -> str:
    """Run one scenario, or dry-run it. The name comes from the form and is used for one
    thing only — a lookup in the config; the command itself is never taken from a request."""
    what = (form.get("action") or [""])[0]
    name = (form.get("name") or [""])[0]
    item = prompt_screen.by_name(name)
    if not item:
        return f"Не знаю сценарію «{name[:40]}»."
    if what == "dry":
        cmd = [str(x) for x in (item.get("dry") or [])]
        if not cmd:
            return f"У «{name}» сухого прогону немає."
        ok, said = run_script(*_resolve(cmd), timeout=900, cap=4000, tail=True)
        return (f"Сухий прогін «{name}»:\n{said}" if ok
                else f"Сухий прогін «{name}» не вдався: {said}")
    if what != "run":
        return "Невідома дія."
    cmd = _resolve([str(x) for x in (item.get("cmd") or [])])
    if not cmd:
        return f"У «{name}» немає команди."
    if not item.get("detach"):
        ok, said = run_script(*cmd, timeout=600, cap=4000, tail=True)
        return (f"«{name}»: {said}" if ok else f"«{name}» не вдався: {said}")
    # A digest or a forecast runs for minutes; detached, the request returns at once and
    # the run survives a panel restart (the same path Zirka's recalc takes).
    unit = "noos-panel-run-" + "".join(c if c.isalnum() else "-" for c in name)[:40]
    ok, said = run_script("systemd-run", "--user", f"--unit={unit}", "--collect",
                          "--setenv", f"HOME={HOME.parent}", *cmd, timeout=60)
    if not ok and "exists" in said:
        return f"«{name}» уже виконується."
    return (f"«{name}» запущено відчепленим; результат прийде туди, куди він пише завжди."
            if ok else f"Не запустилось: {said}")


def _resolve(cmd: list[str]) -> list[str]:
    """A relative path in a configured command means "in this repository", and a `.py`
    means the project's interpreter — so the config stays short and never hardcodes paths."""
    out = []
    for i, part in enumerate(cmd):
        if i == 0 and part.endswith(".py"):
            out.append(str(HOME / ".venv-voice" / "bin" / "python"))
        out.append(str(HOME / part) if not part.startswith(("-", "/")) and
                   (HOME / part).exists() else part)
    return out


def schedule_action(form: dict) -> str:
    """Rewrite a timer's `OnCalendar` lines (t1103).

    The order is the whole design: validate with systemd's own parser, keep a version, write,
    reload, then check the unit still loads — and if it does not, restore and reload again.
    A panel that can break a timer must be able to put it back without a human, because the
    symptom of a broken timer is silence.
    """
    unit = (form.get("unit") or [""])[0].strip()
    allowed = set(data.timer_units())
    if unit not in allowed:
        return f"Не знаю таймера «{unit[:60]}» — редагую лише свої."
    specs = [s.strip() for s in
             (form.get("calendar") or [""])[0].replace(",", "\n").splitlines()
             if s.strip()]
    if not specs:
        return "Розкладу не названо."
    for spec in specs:
        ok, said = run_script("systemd-analyze", "calendar", spec, timeout=20)
        if not ok:
            return f"systemd не приймає «{spec[:40]}»: {said.splitlines()[0] if said else ''}"
    target = UNIT_DIR / unit
    try:
        before = target.read_text(encoding="utf-8")
        body = rules_screen.replace_calendar(before, specs)
    except OSError as exc:
        return f"Юніт не прочитався: {exc}"
    except ValueError as exc:
        return str(exc)
    try:
        atomic_write_text(target, body)
    except OSError as exc:
        return f"Не записалось: {exc}"
    run_script("systemctl", "--user", "daemon-reload", timeout=30)
    ok, said = run_script("systemctl", "--user", "show", unit, "--property=LoadState",
                          timeout=20)
    if "LoadState=loaded" not in (said or ""):
        atomic_write_text(target, before)
        run_script("systemctl", "--user", "daemon-reload", timeout=30)
        return (f"{unit} перестав завантажуватись — повернув попередній юніт і "
                f"перезавантажив systemd. Нічого не змінилось.")
    run_script("systemctl", "--user", "restart", unit, timeout=30)
    return f"{unit}: розклад тепер {', '.join(specs)}. Попередній юніт — у .versions."


def rules_action(form: dict) -> str:
    """Screen 8's writes (t1102): one setting at a time, into `config.local.json`.

    Every refusal is `rules_screen`'s to make — masked values, permissions, lists and
    unknown keys never reach a write — so this function only routes.
    """
    what = (form.get("action") or [""])[0]
    key = (form.get("key") or [""])[0].strip()
    if what == "save":
        ok, said = rules_screen.set_setting(key, (form.get("value") or [""])[0])
        return said if ok else f"Не записано: {said}"
    if what == "reset":
        ok, said = rules_screen.reset_setting(key)
        return said if ok else f"Не скинуто: {said}"
    if what == "schedule":
        return schedule_action(form)
    return "Невідома дія."


def journal_text(unit: str, limit: int | None = None) -> str:
    """The tail of one unit's journal, for a unit systemd itself named.

    The unit arrives in a query string, so it is never trusted into a command line: the
    only accepted names are the timers `systemctl` reported and their services. Without
    that check this link is an argument injection into `journalctl` on a port with no
    login — `-u` is not the only flag it would take.
    """
    allowed = set()
    for t in data.timer_units():
        allowed.add(t)
        allowed.add(t.replace(".timer", ".service"))
    if unit not in allowed:
        return f"Не знаю юніта «{unit}» — показую лише свої таймери та їхні сервіси."
    n = int(limit or conf("panel.journal_lines", 40))
    cmd = ["journalctl", "--user", "-u", unit, "-n", str(n),
           "--no-pager", "--output=short-iso"]
    if not journal_full():
        # A headless unit's stdout IS the content the model composed — the digest's calendar
        # block, mail subjects, the nightly review's findings — and this port has no login
        # (t1094). systemd's own lines carry the diagnostic (Starting / Finished / Failed /
        # exit code) and nothing personal. Priority filtering was measured and does not
        # separate them: a script's stdout is logged at the same priority 6.
        cmd += ["-t", "systemd"]
    ok, said = run_script(*cmd, timeout=30,
                          cap=int(conf("panel.journal_chars", 12000)), tail=True)
    return said if ok else f"Журнал не прочитався: {said}"


def journal_full() -> bool:
    """Is the pane allowed to show a unit's own output? `systemd` (default) says no.

    Kept in config rather than in code so the day the panel has authentication — phase 10 —
    the full journal is one setting away instead of a patch."""
    return str(conf("panel.journal_scope", "systemd")).lower() == "full"


def _boot_epoch() -> float | None:
    """When this machine booted, as a unix timestamp — the origin an interval timer's
    next-elapse is measured from (t1095). Unreadable uptime means no date rather than a
    wrong one."""
    try:
        import time
        return time.time() - float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _raw_config() -> tuple[dict, dict]:
    """`config.json` and `config.local.json` unmerged — the screen's whole point is
    showing which of the two won, which the merged view cannot say."""
    out = []
    for name in ("config.json", "config.local.json"):
        try:
            out.append(json.loads((HOME / name).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            out.append({})
    return out[0], out[1]


def _settings_files() -> list[tuple[str, dict]]:
    """Where a permission allow/deny list could live. All four are absent on this machine,
    and saying so is the point (t1090)."""
    found = []
    for label, f in (("~/.claude/settings.json", Path.home() / ".claude/settings.json"),
                     ("~/.claude/settings.local.json",
                      Path.home() / ".claude/settings.local.json"),
                     (".claude/settings.json", HOME / ".claude/settings.json"),
                     (".claude/settings.local.json", HOME / ".claude/settings.local.json")):
        try:
            found.append((label, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return found


def permission_levels() -> dict:
    """`{key: (level, what)}` for the Rules screen — read through the same module the
    system prompt is rendered from, so the screen cannot drift from what the session is
    told."""
    try:
        sys.path.append(str(HOME / "tools"))
        import permissions as perm_tool                                 # noqa: E402
        current = perm_tool.levels()
        return {key: (perm_tool.LEVELS[perm_tool.level(key, current)], meta["what"])
                for key, meta in perm_tool.DECISIONS.items()}
    except Exception:                                                   # noqa: BLE001
        return {}


def rules_html(unit: str = "", message: str = "") -> str:
    """Screen 8. Read-only — no form, no write path, nothing to press but a journal link."""
    default, local = _raw_config()
    try:
        start = (HOME / "start.sh").read_text(encoding="utf-8")
    except OSError:
        start = ""
    timers = [(u,
               data.show(u, "Unit,Description,TimersCalendar,TimersMonotonic,Persistent,"
                            "NextElapseUSecRealtime,NextElapseUSecMonotonic,"
                            "LastTriggerUSec,ActiveState"),
               data.show(u.replace(".timer", ".service"),
                         "Description,ExecStart,Result,ExecMainStatus,ActiveState"))
              for u in data.timer_units()]
    return render.render_rules(
        rules_screen.setting_rows(default, local, rules_screen.masked_keys()),
        rules_screen.permissions(start, _settings_files(),
                                 conf("telegram.inbox", {}) or {},
                                 levels=permission_levels()),
        rules_screen.schedule_rows(timers, boot_epoch=_boot_epoch()),
        rules_screen.key_rows(rules_screen.key_files()),
        journal_text(unit) if unit else "", unit, filtered=not journal_full(),
        token=FORM_TOKEN, message=message)


class Handler(BaseHTTPRequestHandler):
    server_version = "noos-panel"

    def end_headers(self) -> None:                                       # noqa: N802
        # no response of this panel may be framed: the token and Host checks stop
        # cross-origin posting, but an iframe with an overlaid decoy fires same-origin
        # POSTs carrying the live token the framed page embeds (t1085)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        super().end_headers()

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        return valid_session(cookie_token(self.headers.get("Cookie")))

    def do_GET(self) -> None:                                            # noqa: N802
        path = self.path.split("?")[0]
        try:
            if not host_ok(self.headers.get("Host")):
                return self._send(403, "Невідомий Host — запит не до цієї панелі."
                                  .encode("utf-8"), "text/plain; charset=utf-8")
            # the gate, before anything is read or gathered (t1100)
            if path == "/login":
                return self._send(200, render.render_login(configured()).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/logout":
                drop_session(cookie_token(self.headers.get("Cookie")))
                return self._redirect("/login")
            if not open_path(path) and not self._authed():
                return self._redirect("/login")
            if path.startswith("/static/"):
                found = static_file(path[len("/static/"):])
                if not found:
                    return self._send(404, b"not found", "text/plain; charset=utf-8")
                return self._send(200, found[0], found[1])
            if path == "/":
                return self._send(200, pulse_html().encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/changes":
                query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("q", [""])[0]
                return self._send(200, changes_html(query[:200]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/bruno":
                query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("q", [""])[0]
                return self._send(200, bruno_html(query[:80]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/tasks":
                message = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("m", [""])[0]
                return self._send(200, tasks_html(message[:500]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/memory":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return self._send(
                    200, memory_html(q.get("q", [""])[0][:120],
                                     q.get("m", [""])[0][:300]).encode("utf-8"),
                    "text/html; charset=utf-8")
            if path == "/sources":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return self._send(
                    200, sources_html(q.get("q", [""])[0][:80],
                                      q.get("order", ["activity"])[0][:10],
                                      q.get("m", [""])[0][:300],
                                      q.get("p", [""])[0][:300]).encode("utf-8"),
                    "text/html; charset=utf-8")
            if path == "/zirka":
                day = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("day", [""])[0]
                return self._send(200, zirka_html(day[:10]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/prompt":
                message = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("m", [""])[0]
                return self._send(200, prompt_html(message[:400]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/scenarios":
                message = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("m", [""])[0]
                return self._send(200, scenarios_html(message[:2000]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/rules":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return self._send(200, rules_html(q.get("unit", [""])[0][:80],
                                                  q.get("m", [""])[0][:300])
                                  .encode("utf-8"), "text/html; charset=utf-8")
            if path in SOON:
                html = render.render_soon(TITLES.get(path, path), path, SOON[path])
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                                # noqa: BLE001
            # A panel that 500s with a stack trace is still a panel; one that dies is not.
            traceback.print_exc()
            self._send(500, b"panel error, see the log", "text/plain; charset=utf-8")

    def _redirect(self, where: str) -> None:
        """Post/Redirect/Get. Every write on this panel goes to an append-only store, so
        leaving the submission as the browser's current page means one F5 repeats it
        (t1078) — and an added fact or a closed task cannot be un-repeated."""
        self.send_response(303)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:                                           # noqa: N802
        path = self.path.split("?")[0]
        try:
            # before the token: a rebound page can read the token, but not fake the Host
            if not host_ok(self.headers.get("Host")):
                return self._send(403, "Невідомий Host — запит не до цієї панелі."
                                  .encode("utf-8"), "text/plain; charset=utf-8")
            length = min(int(self.headers.get("Content-Length") or 0),
                         int(conf("panel.max_post_bytes", 1_000_000)))
            body = self.rfile.read(length).decode("utf-8", "replace")
            form = urllib.parse.parse_qs(body, keep_blank_values=True)
            if path == "/login":
                # The one POST without a session or a form token: there is no page of ours
                # to have minted one yet. Rate limiting is what guards it instead (t1100).
                token = try_login((form.get("password") or [""])[0],
                                  self.client_address[0] if self.client_address else "?")
                if not token:
                    said = ("Пароля немає — дивись інструкцію нижче." if not configured()
                            else "Не той пароль, або адреса тимчасово заблокована.")
                    return self._send(
                        403, render.render_login(configured(), said).encode("utf-8"),
                        "text/html; charset=utf-8")
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", cookie_header(token))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not self._authed():
                # refused before any action runs, not after
                return self._send(403, "Потрібен вхід у панель.".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            if not check_token((form.get("token") or [""])[0]):
                # no login guards this port, so an unrecognised form is the only signal
                # that the request did not come from a page this process served
                return self._send(403, "Форма не з цієї панелі.".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            # /bruno is read-only in phase 4 — it has no form, so a POST to it is not
            # a page of ours and falls through to 404 below.
            if path == "/tasks":
                # Post/Redirect/Get: these buttons write to the append-only task log, and
                # a 200 here leaves the submission as the browser's current page — one F5
                # and the add runs twice, uncleanably (t1078). The result rides the query.
                message = tasks_action(form)
                self.send_response(303)
                self.send_header("Location",
                                 "/tasks?m=" + urllib.parse.quote(message[:500]))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/memory":
                # same reason as /tasks: adding or deleting a fact must not repeat on F5
                return self._redirect("/memory?m=" +
                                      urllib.parse.quote(memory_action(form)[:300]))
            if path == "/sources":
                message, probe = sources_action(form)
                where = "/sources?"
                if message:
                    where += "m=" + urllib.parse.quote(message[:300]) + "&"
                if probe:
                    where += "p=" + urllib.parse.quote(probe[:300]) + "&"
                return self._redirect(where.rstrip("&?") or "/sources")
            if path == "/prompt":
                # Post/Redirect/Get: an F5 must not re-save a file (t1078)
                return self._redirect("/prompt?m=" +
                                      urllib.parse.quote(prompt_action(form)[:400]))
            if path == "/rules":
                # Post/Redirect/Get, like every other write on this panel (t1078)
                return self._redirect("/rules?m=" +
                                      urllib.parse.quote(rules_action(form)[:300]))
            if path == "/scenarios":
                # Post/Redirect/Get: a run must not re-fire on F5 (t1078).
                return self._redirect("/scenarios?m=" +
                                      urllib.parse.quote(scenario_action(form)[:2000]))
            if path == "/zirka":
                message = zirka_action(form)
                day = (form.get("day") or [""])[0]
                return self._send(200, zirka_html(day[:10], message).encode("utf-8"),
                                  "text/html; charset=utf-8")
            self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                                # noqa: BLE001
            traceback.print_exc()
            self._send(500, b"panel error, see the log", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):                                   # quieter journal
        sys.stderr.write("panel %s\n" % (fmt % args))


def resolve_host(host: str) -> str:
    """`panel.host`, with `tailscale` meaning this machine's address on the tailnet.

    The owner works from another computer, so loopback alone makes the panel unreachable
    for the only person it is for (2026-10-31). The tailnet is the narrowest network that
    still solves that: his own devices, nothing else — binding to 0.0.0.0 would publish an
    unauthenticated board to the whole home Wi-Fi, which is a different decision.

    The address is resolved at start rather than written into the config, because a
    hardcoded tailnet IP turns into a service that will not start the day it changes. If
    Tailscale is not up, we fall back to loopback and say so: a panel listening somewhere
    safe beats a unit that refuses to boot.
    """
    if host != "tailscale":
        return host
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True,
                             timeout=10)
        found = (out.stdout or "").strip().splitlines()
        if out.returncode == 0 and found:
            return found[0].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    print("tailscale не відповів — слухаю лише 127.0.0.1", file=sys.stderr)
    return "127.0.0.1"


def main() -> int:
    ap = argparse.ArgumentParser(description="адмін-панель Нооса")
    ap.add_argument("--port", type=int, default=int(conf("panel.port", 8091)))
    ap.add_argument("--host", default=str(conf("panel.host", "127.0.0.1")))
    ap.add_argument("--once", action="store_true", help="віддати одну відповідь і вийти")
    args = ap.parse_args()
    args.host = resolve_host(args.host)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"панель на http://{args.host}:{args.port}")
    if args.once:
        httpd.handle_request()
        return 0
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
