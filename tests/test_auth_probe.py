"""t1187 — a lost Claude login must reach the owner, not sit silently in the tmux pane.

The `auth` probe reads the pane and judges the latest event only; the watcher delivers the
alert once per incident through notify.sh (the Bot API, no Claude involved)."""
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
sys.path.insert(0, str(ROOT / "status"))

_spec = importlib.util.spec_from_file_location("noos_auth_probe", ROOT / "status" / "probes" / "auth.py")
auth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auth)

from tools import authcheck  # noqa: E402

watch = importlib.import_module("watch")

EXPIRED = (DATA / "pane-login-expired.txt").read_text(encoding="utf-8")
HEALTHY = (DATA / "pane-healthy.txt").read_text(encoding="utf-8")


def test_expired_pane_is_an_alert_with_the_fix():
    """TC1: the captured outage pane → alert, expired, and the text says how to fix it."""
    p = auth.probe(EXPIRED)
    assert p["id"] == "auth"
    assert p["severity"] == "alert"
    assert p["value"]["expired"] is True
    for needle in ("ssh", "tmux attach -t claude", "/login"):
        assert needle in p["text"]
    # the spoken copy carries no Latin script — the synthesizer would mangle it
    assert not any("a" <= c.lower() <= "z" for c in p["voice"])


def test_healthy_pane_is_silent(tmp_path):
    """TC2: ordinary replies and tool calls → info, not expired. The login itself is faked
    healthy, so the t1188 expiry check does not read this machine's credentials."""
    creds = tmp_path / "credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"refreshToken": "r"}}))
    p = auth.probe(HEALTHY, creds_path=creds, fallback_path=tmp_path / "none")
    assert p["severity"] == "info"
    assert p["value"]["expired"] is False


def test_only_the_latest_event_counts():
    """TC3: an old error followed by a normal reply, or by Login successful, is healthy; a
    reply that merely talks about the error is healthy too."""
    assert not authcheck.pane_expired(EXPIRED + "\n● Готово, я знову тут.\n")
    assert not authcheck.pane_expired(EXPIRED + "\n❯ /login\n  ⎿  Login successful\n")
    assert not authcheck.pane_expired(
        "● Ноос мовчав, бо в терміналі було «Login expired · Please run /login».\n")


def test_cli_error_lines_are_detected():
    """TC4: the CLI's own error line and an API 401 bullet both count."""
    assert authcheck.pane_expired(
        "Failed to authenticate: OAuth session expired and could not be refreshed\n")
    assert authcheck.pane_expired(
        '● API Error: 401 {"type":"error","error":{"message":"OAuth token has expired"}}\n')


def test_no_tmux_session_is_not_a_login_alert(monkeypatch):
    """TC5: capture failed (no session) → unknown, never a false login alert."""
    monkeypatch.setattr(auth, "capture", lambda: None)
    p = auth.probe()
    assert p["severity"] == "info"
    assert p["value"]["expired"] is None


def _fake_run(probes, calls):
    """Fakes watch.run_bounded (t1201): run.sh answers with the probe list, notify.sh with 0."""
    def run(cmd, timeout=None):
        calls.append(cmd)
        if str(cmd[0]).endswith("run.sh"):
            return 0, json.dumps(probes, ensure_ascii=False)
        return 0, ""
    return run


def test_watcher_sends_once_and_speaks_the_voice_copy(monkeypatch, tmp_path):
    """TC6: first tick sends with --voice-text, the next tick within the cooldown is silent."""
    monkeypatch.setattr(watch, "STATE", tmp_path / "watch.json")
    p = auth.probe(EXPIRED)
    calls = []
    monkeypatch.setattr(watch, "run_bounded", _fake_run([p], calls))
    watch.main()
    sends = [c for c in calls if str(c[0]).endswith("notify.sh")]
    assert len(sends) == 1
    cmd = sends[0]
    assert "--voice-text" in cmd
    assert cmd[cmd.index("--voice-text") + 1].endswith(p["voice"])
    assert "tmux attach -t claude" in cmd[-1]

    calls.clear()
    watch.main()
    assert not [c for c in calls if str(c[0]).endswith("notify.sh")], "повтор у межах кулдауну"


def test_auth_is_in_the_watchers_default_list():
    """TC6: the timer runs watch.py with no arguments, so `auth` must be a default."""
    assert "auth" in watch.DEFAULT_PROBES


def test_indented_quote_of_error_is_not_an_event():
    """t1189 TC1: a reply quoting the error on its own indented continuation line is a
    reply, not the CLI's error output — only a column-0 line can be the CLI speaking."""
    assert not authcheck.pane_expired(
        "● Ось що було в терміналі:\n"
        "  Login expired · Please run /login\n"
        "  Тепер усе знову працює.\n")


def test_capture_rejoins_wrapped_lines(monkeypatch):
    """t1189 TC2: capture-pane must pass -J, so a reply soft-wrapped by the terminal is
    rejoined with its bullet instead of leaving the quoted error on a column-0 line."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(auth.subprocess, "run", fake_run)
    auth.capture()
    assert "-J" in seen["cmd"]
