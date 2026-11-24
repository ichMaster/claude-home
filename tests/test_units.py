"""t1256 — every oneshot unit wrapping a headless `claude -p` run must bound it.

For Type=oneshot systemd defaults TimeoutStartSec to infinity, and a timer elapse while
the unit's job is still active is a no-op — so one wedged headless run silences every
following one with no message anywhere. The units live in ~/.config/systemd/user/, not
the repo; this test is the repo-side guard and skips cleanly on a machine without them.
"""
from pathlib import Path

import pytest

UNIT_DIR = Path.home() / ".config" / "systemd" / "user"

# The scripts that exec `claude -p`; each unit wrapping one must carry the bound.
HEADLESS_SCRIPTS = (
    "digest-headless.sh", "social-headless.sh", "youtube-headless.sh",
    "code-review-headless.sh", "mood2.py", "bots/inbox.py",
)


def headless_units():
    if not UNIT_DIR.is_dir():
        return []
    found = []
    for unit in sorted(UNIT_DIR.glob("noos-*.service")):
        text = unit.read_text()
        if any(s in text for s in HEADLESS_SCRIPTS):
            found.append((unit.name, text))
    return found


def test_headless_claude_units_carry_a_timeout():
    units = headless_units()
    if not units:
        pytest.skip("no user units on this machine")
    unbounded = [name for name, text in units if "TimeoutStartSec=" not in text]
    assert unbounded == [], f"oneshot units with infinite TimeoutStartSec: {unbounded}"
