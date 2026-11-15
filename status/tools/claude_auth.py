#!/usr/bin/env python
"""Which Claude credentials should a run use? (t1188)

The regular login (`~/.claude/.credentials.json`) carries everything — inference, the claude.ai
connectors, Remote Control — but its refresh token dies after a few weeks. The year token from
`claude setup-token` lives in a separate file and is inference-only, so it is a fallback and
nothing more: it is used only while the regular login is dead, never instead of a live one.

  login_state(creds, now)            {"alive": bool, "expires": datetime | None}
  env(base, creds, fallback, now)    a copy of `base` with CLAUDE_CODE_OAUTH_TOKEN added if needed
  fallback_file(creds, fallback, now)  the file to source, or None

CLI (for shell callers, via status/tools/claude-auth.sh):
  claude_auth.py fallback-file   prints the path to source, or nothing — never the token
  claude_auth.py status          one human line about the login
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

VAR = "CLAUDE_CODE_OAUTH_TOKEN"


def _creds_path():
    return Path(os.path.expanduser(conf("probes.auth.credentials", "~/.claude/.credentials.json")))


def _fallback_path():
    return Path(os.path.expanduser(conf("probes.auth.fallback_file", "~/.claude/.env.oauth")))


def login_state(creds=None, now=None) -> dict:
    """Alive while the refresh token exists and outlives the safety margin."""
    now = now or datetime.now()
    try:
        o = json.loads(Path(creds or _creds_path()).read_text()).get("claudeAiOauth") or {}
    except (OSError, ValueError, AttributeError):
        return {"alive": False, "expires": None}
    if not o.get("refreshToken"):
        return {"alive": False, "expires": None}
    ms = o.get("refreshTokenExpiresAt")
    if not ms:
        return {"alive": True, "expires": None}
    expires = datetime.fromtimestamp(ms / 1000)
    margin = timedelta(minutes=int(conf("probes.auth.margin_min", 30)))
    return {"alive": expires > now + margin, "expires": expires}


def _read_token(path) -> str:
    try:
        for line in Path(path).read_text().splitlines():
            key, _, value = line.strip().partition("=")
            if key.strip() == VAR and value.strip():
                return value.strip().strip("'\"")
    except OSError:
        pass
    return ""


def fallback_file(creds=None, fallback=None, now=None):
    """The fallback file when the login is dead and the file holds a token, else None."""
    fallback = Path(fallback or _fallback_path())
    if login_state(creds, now)["alive"] or not _read_token(fallback):
        return None
    return fallback


def env(base=None, creds=None, fallback=None, now=None) -> dict:
    """Environment for a `claude -p` subprocess. A token already set is left alone."""
    e = dict(os.environ if base is None else base)
    if e.get(VAR):
        return e
    f = fallback_file(creds, fallback, now)
    if f:
        e[VAR] = _read_token(f)
    return e


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fallback-file", "status"])
    ap.add_argument("--creds")
    ap.add_argument("--fallback")
    a = ap.parse_args(argv)
    if a.cmd == "fallback-file":
        f = fallback_file(a.creds, a.fallback)
        if f:
            print(f)
        return 0
    st = login_state(a.creds)
    when = st["expires"].strftime("%d.%m %H:%M") if st["expires"] else "невідомо"
    spare = "є" if _read_token(Path(a.fallback or _fallback_path())) else "немає"
    print(f"вхід {'живий' if st['alive'] else 'закінчився'}, діє до {when}; запасний токен: {spare}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
