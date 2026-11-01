"""t1100 — admin panel, phase 11: authentication.

The failure mode of this phase is not a leak but a lockout, so the password cases come first.
Everything here is offline: the hash is stdlib, the sessions live in a dict, and the attempt
log is written to a temporary directory.
"""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import auth                                                             # noqa: E402
import render                                                           # noqa: E402
import server                                                           # noqa: E402


# --- TC1-TC3: the password record --------------------------------------------------------

def test_the_right_password_verifies_and_a_wrong_one_does_not():
    record = auth.hash_password("довгий пароль з пробілами")
    assert auth.check_password("довгий пароль з пробілами", record)
    assert not auth.check_password("довгий пароль з пробілам", record)
    assert not auth.check_password("", record)


def test_the_record_holds_nothing_reversible_to_the_password():
    record = auth.hash_password("correct horse battery staple")
    for word in ("correct", "horse", "battery", "staple"):
        assert word not in record
    assert record.startswith("scrypt$")


@pytest.mark.parametrize("record", ["", "scrypt$", "scrypt$a$b$c$d$e", "plain$x$y",
                                    "scrypt$16384$8$1$notthex$alsonothex", "$$$$"])
def test_a_broken_record_verifies_nothing_instead_of_raising(record):
    assert auth.check_password("whatever", record) is False


def test_the_salt_is_random():
    assert auth.hash_password("same") != auth.hash_password("same")


# --- TC4: sessions -----------------------------------------------------------------------

def test_a_fresh_session_is_valid_and_an_expired_one_is_not(monkeypatch):
    # a session is only valid while a password is configured (t1108): clearing the password
    # closes the open sessions, so the fixture has to set one
    monkeypatch.setattr(auth, "stored_record", lambda: auth.hash_password("пароль"))
    monkeypatch.setattr(server, "SESSIONS", {})
    token = server.new_session()
    assert server.valid_session(token)
    server.SESSIONS[token] = time.time() - 1
    assert not server.valid_session(token)


def test_an_unknown_token_is_refused(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS", {})
    assert not server.valid_session("made-up")
    assert not server.valid_session("")


def test_logging_out_drops_the_session(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS", {})
    token = server.new_session()
    server.drop_session(token)
    assert not server.valid_session(token)


# --- TC5-TC6: rate limiting and the log --------------------------------------------------

def attempts_in(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "ATTEMPTS", {})
    monkeypatch.setattr(server, "AUTH_LOG", tmp_path / "panel-auth.jsonl")
    record = auth.hash_password("правильний")
    monkeypatch.setattr(auth, "stored_record", lambda: record)
    return record


def test_five_failures_lock_the_address_even_against_the_right_password(monkeypatch,
                                                                       tmp_path):
    attempts_in(monkeypatch, tmp_path)
    for _ in range(5):
        assert server.try_login("хибний", "192.168.1.9") is None
    assert server.try_login("правильний", "192.168.1.9") is None, \
        "a locked address must stay locked even with the right password"


def test_another_address_is_not_punished_for_it(monkeypatch, tmp_path):
    attempts_in(monkeypatch, tmp_path)
    for _ in range(5):
        server.try_login("хибний", "192.168.1.9")
    assert server.try_login("правильний", "192.168.1.10")


def test_the_lock_expires(monkeypatch, tmp_path):
    attempts_in(monkeypatch, tmp_path)
    for _ in range(5):
        server.try_login("хибний", "192.168.1.9")
    server.ATTEMPTS["192.168.1.9"]["until"] = time.time() - 1
    assert server.try_login("правильний", "192.168.1.9")


def test_a_success_clears_the_counter(monkeypatch, tmp_path):
    attempts_in(monkeypatch, tmp_path)
    server.try_login("хибний", "192.168.1.9")
    server.try_login("правильний", "192.168.1.9")
    assert server.ATTEMPTS.get("192.168.1.9", {}).get("fails", 0) == 0


def test_every_attempt_is_logged_without_the_password(monkeypatch, tmp_path):
    attempts_in(monkeypatch, tmp_path)
    server.try_login("таємний-хибний", "192.168.1.9")
    server.try_login("правильний", "192.168.1.9")
    lines = [json.loads(x) for x in
             (tmp_path / "panel-auth.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["result"] for r in lines] == ["fail", "ok"]
    assert all(r["from"] == "192.168.1.9" for r in lines)
    body = (tmp_path / "panel-auth.jsonl").read_text(encoding="utf-8")
    assert "таємний-хибний" not in body and "правильний" not in body


def test_a_lockout_is_logged_as_such(monkeypatch, tmp_path):
    attempts_in(monkeypatch, tmp_path)
    for _ in range(6):
        server.try_login("хибний", "192.168.1.9")
    results = [json.loads(x)["result"] for x in
               (tmp_path / "panel-auth.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "locked" in results


# --- TC7: fails closed -------------------------------------------------------------------

def test_with_no_password_configured_nothing_is_authenticated(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "stored_record", lambda: "")
    monkeypatch.setattr(server, "ATTEMPTS", {})
    monkeypatch.setattr(server, "AUTH_LOG", tmp_path / "panel-auth.jsonl")
    assert server.try_login("anything", "127.0.0.1") is None
    assert not server.configured()


def test_the_login_page_names_the_command_that_sets_a_password():
    """With no password there is nothing to type, so the page explains instead of asking."""
    html = render.render_login(configured=False)
    assert "panel/auth.py set" in html and 'type="password"' not in html
    ordinary = render.render_login(configured=True)
    assert 'type="password"' in ordinary and "panel/auth.py set" not in ordinary


# --- TC8: what needs a session -----------------------------------------------------------

@pytest.mark.parametrize("path", ["/login", "/static/panel.css", "/static/x.js"])
def test_the_login_page_and_the_stylesheet_need_no_session(path):
    assert server.open_path(path)


@pytest.mark.parametrize("path", ["/", "/rules", "/zirka", "/memory", "/tasks",
                                  "/sources", "/changes", "/bruno", "/logout",
                                  "/static/../.env.voice"])
def test_every_other_path_needs_one(path):
    assert not server.open_path(path)


# --- TC9: the cookie ---------------------------------------------------------------------

def test_the_cookie_is_httponly_samesite_strict_and_rooted():
    value = server.cookie_header("abc123")
    assert value.startswith("noos_panel=abc123")
    for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
        assert flag in value


def test_the_cookie_is_read_back_out_of_a_header():
    assert server.cookie_token("noos_panel=abc123; other=1") == "abc123"
    assert server.cookie_token("other=1") == ""
    assert server.cookie_token(None) == ""


# --- TC10: the CLI writes a protected file ----------------------------------------------

def test_set_writes_mode_600_and_clear_removes_it(tmp_path, monkeypatch):
    target = tmp_path / ".env.panel"
    monkeypatch.setattr(auth, "RECORD_FILE", target)
    auth.save_record(auth.hash_password("пароль"))
    assert target.exists() and oct(target.stat().st_mode & 0o777) == "0o600"
    assert auth.check_password("пароль", auth.stored_record())
    auth.clear_record()
    assert not target.exists() and auth.stored_record() == ""


# --- the gate, end to end over a real socket ---------------------------------------------

@pytest.fixture
def live_panel(monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    record = auth.hash_password("правильний")
    monkeypatch.setattr(auth, "stored_record", lambda: record)
    monkeypatch.setattr(server, "SESSIONS", {})
    monkeypatch.setattr(server, "ATTEMPTS", {})
    monkeypatch.setattr(server, "pulse_html", lambda: "<html>пульс</html>")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def ask(port, method, path, body="", cookie=""):
    """A browser percent-encodes a non-ASCII password; so does this."""
    import http.client
    import urllib.parse
    if body and "=" in body and any(ord(c) > 127 for c in body):
        body = urllib.parse.urlencode(
            dict(part.split("=", 1) for part in body.split("&")))
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/x-www-form-urlencoded"} if body else {}
    if cookie:
        headers["Cookie"] = cookie
    conn.request(method, path, body=body or None, headers=headers)
    r = conn.getresponse()
    text = r.read().decode("utf-8", "replace")
    conn.close()
    return r, text


def test_an_anonymous_visit_lands_on_the_login_page(live_panel):
    r, _ = ask(live_panel, "GET", "/")
    assert r.status == 303 and r.getheader("Location") == "/login"


def test_the_stylesheet_is_served_without_a_session(live_panel):
    r, _ = ask(live_panel, "GET", "/static/panel.css")
    assert r.status == 200


def test_an_anonymous_post_is_refused_and_acts_on_nothing(live_panel, monkeypatch):
    fired = []
    monkeypatch.setattr(server, "tasks_action", lambda form: fired.append(form) or "ok")
    r, _ = ask(live_panel, "POST", "/tasks",
               f"token={server.FORM_TOKEN}&action=add&text=x")
    assert r.status == 403 and fired == []


def test_the_right_password_opens_the_panel(live_panel):
    r, _ = ask(live_panel, "POST", "/login", "password=правильний")
    assert r.status == 303 and r.getheader("Location") == "/"
    cookie = r.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    token = cookie.split(";")[0]
    page, text = ask(live_panel, "GET", "/", cookie=token)
    assert page.status == 200 and "пульс" in text


def test_a_wrong_password_answers_the_login_page_with_403(live_panel):
    r, text = ask(live_panel, "POST", "/login", "password=хибний")
    assert r.status == 403 and "Не той пароль" in text and not r.getheader("Set-Cookie")


def test_logging_out_sends_you_back_to_the_login_page(live_panel):
    r, _ = ask(live_panel, "POST", "/login", "password=правильний")
    token = r.getheader("Set-Cookie").split(";")[0]
    out, _ = ask(live_panel, "GET", "/logout", cookie=token)
    assert out.status == 303
    again, _ = ask(live_panel, "GET", "/", cookie=token)
    assert again.status == 303, "the dropped session must not open anything"


# --- t1108: the HTTP surface itself (full review: security H1, H3, M2, M3, M4) -----------

@pytest.mark.parametrize("header,want", [
    ("10", 10), ("0", 0), ("", 0), (None, 0), ("abc", 0),
    ("-1", 0), ("-999999999", 0),              # H1: a negative length disabled the cap
    ("99999999999", "cap"),
])
def test_the_body_length_can_never_be_negative_or_unbounded(header, want):
    """A negative Content-Length made `min(length, cap)` return the negative number, and
    `rfile.read(-1)` reads until the client stops: one unauthenticated POST took the live
    panel from 24 to 85 MiB, and a private instance to 3.8 GiB in six seconds."""
    cap = int(server.conf("panel.max_post_bytes", 1_000_000))
    got = server.body_length(header)
    assert got >= 0
    assert got == (cap if want == "cap" else want)


def test_the_handler_has_a_read_deadline():
    """M3: a connection that sends headers and then nothing parked a server thread for
    ever — 200 parked and still alive, with no deadline anywhere."""
    assert isinstance(server.Handler.timeout, (int, float)) and 0 < server.Handler.timeout


def test_many_wrong_passwords_at_once_cannot_slip_one_through(monkeypatch, tmp_path):
    """H3: the counter was read and written without a lock, so 43 of 60 attempts in one
    window verified and the right password at slot 60 still got a cookie."""
    import threading
    record = auth.hash_password("правильний")
    monkeypatch.setattr(auth, "stored_record", lambda: record)
    monkeypatch.setattr(server, "ATTEMPTS", {})
    monkeypatch.setattr(server, "SESSIONS", {})
    monkeypatch.setattr(server, "AUTH_LOG", tmp_path / "auth.jsonl")
    got = []

    def attempt(password):
        got.append(server.try_login(password, "192.168.1.9"))

    threads = [threading.Thread(target=attempt, args=("хибний",)) for _ in range(30)]
    threads.append(threading.Thread(target=attempt, args=("правильний",)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for g in got if g) <= 1, "at most the one correct password may pass"
    assert server.try_login("правильний", "192.168.1.9") is None, "and then it is locked"


def test_the_attempt_log_cannot_be_grown_without_bound(monkeypatch, tmp_path):
    """M2: the unauthenticated endpoint appended a line per request — 5.9 GiB a day
    measured, on a disk with 13.7 GiB free. A locked address stops writing lines."""
    log = tmp_path / "auth.jsonl"
    monkeypatch.setattr(auth, "stored_record", lambda: auth.hash_password("правильний"))
    monkeypatch.setattr(server, "ATTEMPTS", {})
    monkeypatch.setattr(server, "AUTH_LOG", log)
    for _ in range(500):
        server.try_login("хибний", "192.168.1.9")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 20, f"{len(lines)} lines for 500 attempts from one address"
    assert any("locked" in line for line in lines)


def test_clearing_the_password_closes_the_open_sessions(monkeypatch):
    """M4: `auth.py clear` says the panel lets nobody in, and every live session kept
    working for its full twelve hours."""
    monkeypatch.setattr(server, "SESSIONS", {})
    monkeypatch.setattr(auth, "stored_record", lambda: auth.hash_password("правильний"))
    token = server.new_session()
    assert server.valid_session(token)
    monkeypatch.setattr(auth, "stored_record", lambda: "")
    assert not server.valid_session(token)
