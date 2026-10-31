#!/usr/bin/env python
"""One-time OAuth login to read your own YouTube subscriptions (t1040).

Run this once, by the owner, in the terminal. It opens Google's consent screen via the
loopback flow, exchanges the code for a refresh token, and appends the three values to
`.env.youtube` (mode 600, git-ignored). After that `status/tools/youtube_subs.py` can read
subscriptions daily with no further login.

Prerequisites (owner, one time, in Google Cloud Console):
  1. Create a project, enable "YouTube Data API v3".
  2. OAuth consent screen: External, add yourself as a test user.
  3. Credentials → Create OAuth client ID → type "Desktop app". Note the client id/secret.

Then:  YT_CLIENT_ID=... YT_CLIENT_SECRET=... status/tools/youtube_oauth.py
(or put the two in .env.youtube first and run with no env). A browser opens; approve; done.

If this box has no browser, run it with SSH local-forwarding the loopback port, e.g.
  ssh -L 8765:localhost:8765 picobox
and open the printed URL in your laptop's browser — the redirect reaches the forwarded port.
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

HOME = Path(__file__).resolve().parents[2]
ENV = HOME / ".env.youtube"
SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PORT = int(os.environ.get("YT_OAUTH_PORT", "8765"))


def read_env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def main() -> int:
    env = read_env()
    cid = os.environ.get("YT_CLIENT_ID") or env.get("YT_CLIENT_ID")
    csec = os.environ.get("YT_CLIENT_SECRET") or env.get("YT_CLIENT_SECRET")
    if not cid or not csec:
        print("Спершу задай YT_CLIENT_ID і YT_CLIENT_SECRET (у .env.youtube або в середовищі). "
              "Див. шапку цього файлу — як створити OAuth-клієнт Desktop у Google Cloud.")
        return 2

    redirect = f"http://localhost:{PORT}/"
    params = {"client_id": cid, "redirect_uri": redirect, "response_type": "code",
              "scope": SCOPE, "access_type": "offline", "prompt": "consent"}
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    code_box: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                                # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code_box["code"] = (q.get("code") or [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write("Готово, можна закрити вкладку.".encode("utf-8"))

        def log_message(self, *a):                                       # silence
            pass

    srv = http.server.HTTPServer(("localhost", PORT), Handler)
    srv.socket.settimeout(300)
    print("Відкрий у браузері (або через ssh -L):\n" + url)
    try:
        webbrowser.open(url)
    except Exception:                                                    # noqa: BLE001
        pass
    threading.Thread(target=srv.handle_request, daemon=True).start()
    print(f"Чекаю на підтвердження на {redirect} (до 5 хв)…")
    try:
        srv.socket.settimeout(300)
        while "code" not in code_box:
            threading.Event().wait(0.5)
    except (KeyboardInterrupt, socket.timeout):
        print("не дочекався коду"); return 1
    code = code_box.get("code")
    if not code:
        print("код не отримано"); return 1

    body = urllib.parse.urlencode({
        "code": code, "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read())
    refresh = tok.get("refresh_token")
    if not refresh:
        print("Google не повернув refresh_token — прибери доступ застосунку в акаунті "
              "й повтори (потрібен prompt=consent).")
        return 1

    lines = {**read_env(), "YT_CLIENT_ID": cid, "YT_CLIENT_SECRET": csec,
             "YT_REFRESH_TOKEN": refresh}
    ENV.write_text("".join(f"{k}={v}\n" for k, v in lines.items()), encoding="utf-8")
    ENV.chmod(0o600)
    print(f"Збережено в {ENV}. Тепер щоденна джоба читатиме підписки сама.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
