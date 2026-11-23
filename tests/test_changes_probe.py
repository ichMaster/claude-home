"""t1245 — an empty day argument to changes.py means today, not a day named «».

The 23:30 timer runs `changes-send.sh` with no argument, and the script passes
`"${1:-}"` — an empty string — into changes.py, which took it verbatim and looked
for `changelog/.jsonl`. The probe is run as a real subprocess; it only reads the
changelog directory, so nothing is sent or written.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "status" / "probes" / "changes.py"


def run_probe(*args):
    res = subprocess.run([sys.executable, str(PROBE), *args],
                         capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_empty_day_argument_means_today():
    """t1245 TC1: argv[1]="" reads as today, never as a day named «»."""
    out = run_probe("")
    today = datetime.now().strftime("%Y-%m-%d")
    assert out["value"]["day"] == today
    assert "Змін за  немає" not in out["text"]


def test_explicit_date_still_honoured():
    """t1245 TC2: a real date argument is used as given."""
    out = run_probe("1999-01-02")
    assert out["value"]["day"] == "1999-01-02"
