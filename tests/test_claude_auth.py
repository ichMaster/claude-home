"""t1188 — the long-lived token stands in only when the regular Claude login is gone.

The year token from `claude setup-token` is inference-only (no claude.ai connectors, no
Remote Control), so it must never shadow a live login; and a dying login is announced before
it dies."""
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status"))

from tools import claude_auth  # noqa: E402

_spec = importlib.util.spec_from_file_location("noos_auth_probe_t1188",
                                               ROOT / "status" / "probes" / "auth.py")
auth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auth)

HEALTHY_PANE = (ROOT / "tests" / "data" / "pane-healthy.txt").read_text(encoding="utf-8")
TOKEN = "sk-ant-oat01-" + "x" * 95
NOW = datetime(2026, 11, 15, 16, 0)


def creds(tmp_path, days=None, refresh="r" * 20):
    o = {"accessToken": "a", "refreshToken": refresh}
    if days is not None:
        o["refreshTokenExpiresAt"] = int((NOW + timedelta(days=days)).timestamp() * 1000)
    p = tmp_path / "credentials.json"
    p.write_text(json.dumps({"claudeAiOauth": o}))
    return p


def fallback(tmp_path, token=TOKEN):
    p = tmp_path / "env.oauth"
    p.write_text(f"CLAUDE_CODE_OAUTH_TOKEN={token}\n" if token is not None else "")
    return p


def test_live_login_needs_no_fallback(tmp_path):
    """TC1"""
    c, f = creds(tmp_path, days=20), fallback(tmp_path)
    assert claude_auth.login_state(c, NOW)["alive"] is True
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_auth.env({}, c, f, NOW)
    assert claude_auth.fallback_file(c, f, NOW) is None


def test_dead_login_uses_the_token(tmp_path):
    """TC2: expired, empty refresh token, missing file — all fall back."""
    f = fallback(tmp_path)
    for c in (creds(tmp_path, days=-1), creds(tmp_path, days=5, refresh=""),
              tmp_path / "missing.json"):
        assert claude_auth.login_state(c, NOW)["alive"] is False
        assert claude_auth.env({}, c, f, NOW)["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
        assert claude_auth.fallback_file(c, f, NOW) == f


def test_dead_login_and_no_token(tmp_path):
    """TC3"""
    c = creds(tmp_path, days=-1)
    for f in (tmp_path / "none", fallback(tmp_path, token=None), fallback(tmp_path, token="")):
        assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_auth.env({}, c, f, NOW)
        assert claude_auth.fallback_file(c, f, NOW) is None


def test_existing_env_token_is_kept(tmp_path):
    """TC4"""
    c, f = creds(tmp_path, days=-1), fallback(tmp_path)
    assert claude_auth.env({"CLAUDE_CODE_OAUTH_TOKEN": "mine"}, c, f, NOW)[
        "CLAUDE_CODE_OAUTH_TOKEN"] == "mine"


def _latin(s):
    return any("a" <= ch.lower() <= "z" for ch in s)


def test_probe_warns_before_and_after_expiry(tmp_path):
    """TC5 + TC6"""
    f = fallback(tmp_path)
    ok = auth.probe(HEALTHY_PANE, creds_path=creds(tmp_path, days=20), fallback_path=f, now=NOW)
    assert ok["severity"] == "info"

    for days in (2, -1):
        p = auth.probe(HEALTHY_PANE, creds_path=creds(tmp_path, days=days),
                       fallback_path=f, now=NOW)
        assert p["severity"] == "warn"
        assert "/login" in p["text"]
        assert not _latin(p["voice"])
        assert TOKEN not in json.dumps(p, ensure_ascii=False)
    # running on the fallback is said out loud — connectors are gone
    assert "запасн" in p["text"]


def test_cli_never_prints_the_token(tmp_path):
    """TC6: the shell helper only ever learns a path."""
    c, f = creds(tmp_path, days=-1), fallback(tmp_path)
    out = subprocess.run([sys.executable, str(ROOT / "status" / "tools" / "claude_auth.py"),
                          "fallback-file", "--creds", str(c), "--fallback", str(f)],
                         capture_output=True, text=True)
    assert out.stdout.strip() == str(f)
    assert TOKEN not in out.stdout + out.stderr
