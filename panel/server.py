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
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME))
sys.path.insert(0, str(HOME / "panel"))

from noosconf import conf                                               # noqa: E402
import data                                                            # noqa: E402
import render                                                          # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
# screen → the phase that builds it, for the placeholder pages
SOON = {
    "/changes": "фаза 2", "/zirka": "фаза 3", "/bruno": "фаза 4",
    "/prompt": "фаза 5", "/scenarios": "фаза 5", "/tasks": "фаза 6",
    "/memory": "фаза 7", "/sources": "фаза 7", "/rules": "фаза 8",
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


def main() -> int:
    ap = argparse.ArgumentParser(description="адмін-панель Нооса")
    ap.add_argument("--port", type=int, default=int(conf("panel.port", 8091)))
    ap.add_argument("--host", default=str(conf("panel.host", "127.0.0.1")))
    ap.add_argument("--once", action="store_true", help="віддати одну відповідь і вийти")
    args = ap.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"панель на http://{args.host}:{args.port}")
    if args.once:
        httpd.handle_request()
        return 0
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
