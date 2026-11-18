"""t1203 — the digest part (ранковий/вечірній) comes from the clock when no argument is
given; an explicit argument still wins (the /digest command passes it by hand).

The `claude` binary is stubbed on PATH: it records the prompt it was handed and exits, so
the test runs the real script end to end with nothing sent and no model called.
NOOS_DIGEST_HOUR pins the hour the script would otherwise take from `date +%H`.
"""
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_script(tmp_path, hour, *args):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    out = tmp_path / "prompt.txt"
    stub = bin_dir / "claude"
    stub.write_text("#!/usr/bin/env bash\n"
                    f"printf '%s' \"$2\" > {out}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
               NOOS_DIGEST_HOUR=hour)
    res = subprocess.run(["bash", str(ROOT / "status" / "digest-headless.sh"), *args],
                         capture_output=True, text=True, env=env, timeout=60)
    assert res.returncode == 0, res.stderr
    return out.read_text()


def test_no_argument_evening_hour_builds_evening(tmp_path):
    """TC1 (regression): at 20:03 the timer passes nothing — the prompt must say вечірній."""
    prompt = run_script(tmp_path, "20")
    assert "Build the вечірній digest" in prompt


def test_no_argument_morning_hour_builds_morning(tmp_path):
    """TC2: at 08:03 with no argument the prompt must say ранковий."""
    prompt = run_script(tmp_path, "08")
    assert "Build the ранковий digest" in prompt


def test_explicit_argument_wins(tmp_path):
    """TC3: /digest passes the part by hand; the clock must not override it."""
    prompt = run_script(tmp_path, "08", "вечірній")
    assert "Build the вечірній digest" in prompt
