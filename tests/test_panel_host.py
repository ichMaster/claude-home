"""t1069 — the panel rejects a foreign Host header (DNS rebinding protection).

The form token (t1068) stops a cross-origin page from posting here; rebinding makes the
attacker's page same-origin, so the token can be read and replayed. The Host header is the
one thing a rebinding request cannot fake away: it names the attacker's own domain.
"""
import http.client
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import server                                                           # noqa: E402


# --- TC1: the rule itself ---------------------------------------------------------------

@pytest.mark.parametrize("host", [
    "127.0.0.1:8091", "192.168.1.5:8091", "192.168.1.5",
    "[::1]:8091", "localhost:8091", "localhost",
    "noos.tail1234.ts.net", "noos.tail1234.ts.net:8091",
    None, "",
])
def test_own_hosts_are_accepted(host):
    assert server.host_ok(host) is True


@pytest.mark.parametrize("host", [
    "evil.example:8091",            # the rebinding case: a DNS name the attacker controls
    "evil.example",
    "panel.evil.example:8091",
    "ts.net.evil.example:8091",     # ".ts.net" must be a suffix match, not a substring
])
def test_dns_names_are_rejected(host):
    assert server.host_ok(host) is False


def test_extra_names_come_from_config(monkeypatch):
    import noosconf
    real = noosconf.conf
    monkeypatch.setattr(server, "conf",
                        lambda key, default=None: ["noos.lan"] if key == "panel.hosts"
                        else real(key, default))
    assert server.host_ok("noos.lan:8091") is True
    assert server.host_ok("evil.example:8091") is False


# --- TC2, TC3: wired into the handlers --------------------------------------------------

@pytest.fixture()
def live_panel():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def fetch(port: int, method: str, path: str, host: str, body: str = ""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host}
    if body:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body or None, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_get_with_foreign_host_is_refused(live_panel):
    status, _ = fetch(live_panel, "GET", "/static/panel.css", "evil.example:8091")
    assert status == 403
    status, _ = fetch(live_panel, "GET", "/static/panel.css", f"127.0.0.1:{live_panel}")
    assert status == 200


def test_post_with_foreign_host_is_refused_even_with_the_token(live_panel):
    """Rebinding lets the attacker read the token first — it must not be proof by itself.

    The action is a deliberately unknown one: if the guard ever regresses, this test must
    not fire a real script at the owner (a first version used `ask` and did exactly that).
    """
    body = f"token={server.FORM_TOKEN}&action=noop-t1069"
    status, _ = fetch(live_panel, "POST", "/zirka", "evil.example:8091", body)
    assert status == 403


# --- t1085: no response of the panel may be framed --------------------------------------

def fetch_resp(port: int, method: str, path: str, body: str = ""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/x-www-form-urlencoded"} if body else {}
    # logged in: since t1100 every path but /login and /static needs a session cookie
    headers["Cookie"] = f"{server.COOKIE}={server.new_session()}"
    conn.request(method, path, body=body or None, headers=headers)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp


def test_pages_refuse_framing(live_panel):
    """t1085 TC1 — the FORM_TOKEN and Host checks stop cross-origin posting, but an iframe
    with an overlaid decoy fires same-origin POSTs with the live token; the browser has to
    be told never to frame the panel at all."""
    r = fetch_resp(live_panel, "GET", "/static/panel.css")
    assert r.getheader("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in (r.getheader("Content-Security-Policy") or "")


def test_redirects_refuse_framing_too(live_panel, monkeypatch):
    """t1085 TC2 — the 303 after a write is a response of the panel like any other."""
    monkeypatch.setattr(server, "memory_action", lambda form: "ok")
    r = fetch_resp(live_panel, "POST", "/memory",
                   f"token={server.FORM_TOKEN}&action=noop-t1085")
    assert r.status == 303
    assert r.getheader("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in (r.getheader("Content-Security-Policy") or "")
