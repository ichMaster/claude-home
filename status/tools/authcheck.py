#!/usr/bin/env python
"""Does this text say the Claude login is gone? Shared by the `auth` probe and the handoff.

  pane_expired(pane)   the always-on session's tmux pane: is its latest event an auth error
  is_auth_error(text)  a `claude -p` answer that is really just the auth error

Only the **latest event** in a pane counts — the last reply bullet (`●`), a CLI error line or
`Login successful` — so an old error in the scrollback is not an outage and a recovered
session goes green by itself. A reply that merely quotes the error mid-sentence is a reply,
not the error (t1187).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

BULLET = "●"


def _patterns():
    return ([s.lower() for s in conf("probes.auth.expired", [])],
            [s.lower() for s in conf("probes.auth.recovered", [])])


def _starts_with_any(text: str, pats) -> bool:
    return any(text.startswith(p) for p in pats)


def classify(line: str):
    """'expired', 'ok' or None (not an event) for one pane line."""
    expired, recovered = _patterns()
    s = line.strip().lower()
    if not s:
        return None
    if any(p in s for p in recovered):
        return "ok"
    if s.startswith(BULLET):
        body = s[len(BULLET):].strip()
        if _starts_with_any(body, expired):
            return "expired"
        # an API error bullet carries the reason inside a JSON blob
        if body.startswith("api error") and any(p in body for p in expired):
            return "expired"
        return "ok"
    # the CLI's own error output is not a bullet
    if _starts_with_any(s, expired):
        return "expired"
    return None


def pane_expired(pane: str) -> bool:
    for line in reversed(pane.splitlines()):
        verdict = classify(line)
        if verdict:
            return verdict == "expired"
    return False


def is_auth_error(text: str) -> bool:
    """A `claude -p` answer whose first line is the auth error."""
    first = next((l for l in text.splitlines() if l.strip()), "")
    return classify(first) == "expired"
