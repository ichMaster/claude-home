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
import subprocess
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "panel"))

from noosconf import conf                                               # noqa: E402
import changes                                                         # noqa: E402
import data                                                            # noqa: E402
import render                                                          # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
# screen → the phase that builds it, for the placeholder pages
SOON = {
    "/zirka": "фаза 3", "/bruno": "фаза 4",
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
            if path in SOON:
                html = render.render_soon(TITLES.get(path, path), path, SOON[path])
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:                                                # noqa: BLE001
            # A panel that 500s with a stack trace is still a panel; one that dies is not.
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
