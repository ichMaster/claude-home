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
import changes                                                         # noqa: E402
import data                                                            # noqa: E402
import render                                                          # noqa: E402
import zirka                                                           # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
# screen → the phase that builds it, for the placeholder pages
SOON = {
    "/bruno": "фаза 4",
    "/prompt": "фаза 5", "/scenarios": "фаза 5", "/tasks": "фаза 6",
    "/memory": "фаза 7", "/sources": "фаза 7", "/rules": "фаза 8",
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


def run_script(*cmd: str, timeout: int = 300) -> tuple[bool, str]:
    """Run one of the project's own scripts. A failure is returned, never swallowed."""
    try:
        out = subprocess.run(list(cmd), capture_output=True, text=True,
                             timeout=timeout, cwd=str(HOME))
    except subprocess.SubprocessError as exc:
        return False, f"не вдалося запустити: {exc}"
    ok = out.returncode == 0
    said = (out.stdout or "").strip() or (out.stderr or "").strip()
    return ok, said[:600]


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


class Handler(BaseHTTPRequestHandler):
    server_version = "noos-panel"

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
            if path == "/zirka":
                day = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get("day", [""])[0]
                return self._send(200, zirka_html(day[:10]).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path in SOON:
                html = render.render_soon(TITLES.get(path, path), path, SOON[path])
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                                # noqa: BLE001
            # A panel that 500s with a stack trace is still a panel; one that dies is not.
            traceback.print_exc()
            self._send(500, b"panel error, see the log", "text/plain; charset=utf-8")

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
