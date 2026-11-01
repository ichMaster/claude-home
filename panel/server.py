#!/usr/bin/env python
"""The admin panel — phase 1: the shell and the Pulse screen.

    panel/server.py [--port 8091] [--once]

Binds `127.0.0.1` only (`panel.host`). There is no authentication and there must not be
one: the panel is reached over an SSH tunnel, and a login form on a loopback socket is
decoration. If it ever needs to be reachable from elsewhere, that is a version of its own
(docs/features/ADMIN-PANEL.md § Technical shape).

Read-only, deliberately. The other nine screens answer with a placeholder naming the phase
that builds them, so the rail is honest rather than full of dead links.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import secrets
import subprocess
import sys
import traceback
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "panel"))

from noosconf import conf                                               # noqa: E402
import bruno                                                           # noqa: E402
import changes                                                         # noqa: E402
import data                                                            # noqa: E402
import memory_screen                                                   # noqa: E402
import render                                                          # noqa: E402
import rules_screen                                                    # noqa: E402
import sources_screen                                                  # noqa: E402
import tasks_screen                                                    # noqa: E402
import zirka                                                           # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
# screen → the phase that builds it, for the placeholder pages
SOON = {
    "/prompt": "фаза 5", "/scenarios": "фаза 5",
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


def rules_html(unit: str = "") -> str:
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
                                 conf("telegram.inbox", {}) or {}),
        rules_screen.schedule_rows(timers, boot_epoch=_boot_epoch()),
        rules_screen.key_rows(rules_screen.key_files()),
        journal_text(unit) if unit else "", unit, filtered=not journal_full())


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

    def do_GET(self) -> None:                                            # noqa: N802
        path = self.path.split("?")[0]
        try:
            if not host_ok(self.headers.get("Host")):
                return self._send(403, "Невідомий Host — запит не до цієї панелі."
                                  .encode("utf-8"), "text/plain; charset=utf-8")
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
            if path == "/rules":
                # GET only: phase 8 reads. A POST falls through to the 404 below, which is
                # the honest answer — this screen has no form to have submitted.
                unit = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("unit", [""])[0]
                return self._send(200, rules_html(unit[:80]).encode("utf-8"),
                                  "text/html; charset=utf-8")
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
