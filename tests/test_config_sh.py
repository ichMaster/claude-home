"""t1231 — config.sh conf() must not execute a key, only look it up.

conf() used to interpolate its argument into the Python one-liner source, so a key
containing a single quote escaped the string literal and ran arbitrary code. The tests
drive conf() through a real bash, with a marker payload that must stay inert.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv-voice" / "bin" / "python"


def run_conf(key):
    return subprocess.run(
        ["bash", "-c", '. "$1/config.sh"; conf "$2"', "-", str(ROOT), key],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin", "NOOS_PYTHON": str(PY)},
    )


def test_single_quote_key_is_inert():
    # TC1: the historical payload — escaped the literal and printed the marker
    payload = "voice.voices.x'); import sys; sys.stderr.write('INJECTED-OK\\n'); ('"
    res = run_conf(payload)
    assert "INJECTED-OK" not in res.stdout + res.stderr
    assert res.stdout.strip() == ""           # behaves like a missing key


def test_ordinary_key_still_resolves():
    # TC2: the same value the Python layer returns
    expected = subprocess.run(
        [str(PY), "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); "
         "from noosconf import conf; v = conf('probes.weather.city'); "
         "print('' if v is None else v)", str(ROOT)],
        capture_output=True, text=True, timeout=30).stdout
    res = run_conf("probes.weather.city")
    assert res.returncode == 0
    assert res.stdout == expected


def test_double_quote_backslash_key_is_inert():
    # TC3: shell/Python escaping edge — no error from the Python layer, empty lookup
    res = run_conf('a"b\\c.__import__("os")')
    assert "Traceback" not in res.stderr
    assert res.stdout.strip() == ""
