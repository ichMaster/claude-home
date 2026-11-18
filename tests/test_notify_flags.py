"""t1202 — notify.sh must refuse an unknown --flag instead of delivering it as the message
(the headless digest really sent voiced «--help» to the owner three mornings running).

The script runs against a fake $HOME: a copy of notify.sh, a fake .env.telegram and a stub
curl on PATH that logs its argv — so nothing real is ever sent, even while the test is red.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fake_home(tmp_path):
    home = tmp_path / "home"
    ch = home / "claude-home"
    ch.mkdir(parents=True)
    shutil.copy2(ROOT / "notify.sh", ch / "notify.sh")
    (ch / ".env.telegram").write_text("TELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_CHAT_ID=1\n")
    # the paragraph splitter needs the venv python; the rest of the helpers may be absent
    (ch / ".venv-voice").symlink_to(ROOT / ".venv-voice")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_log = tmp_path / "curl.log"
    curl = bin_dir / "curl"
    curl.write_text("#!/usr/bin/env bash\n"
                    f"echo \"$@\" >> {curl_log}\n"
                    "echo 200\n")
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
    return home, ch, bin_dir, curl_log


def run_notify(tmp_path, *args):
    home, ch, bin_dir, curl_log = fake_home(tmp_path)
    env = dict(os.environ, HOME=str(home), PATH=f"{bin_dir}:{os.environ['PATH']}")
    res = subprocess.run([str(ch / "notify.sh"), *args],
                         capture_output=True, text=True, env=env, timeout=60)
    sent = curl_log.read_text() if curl_log.exists() else ""
    return res, sent


def test_help_prints_usage_and_sends_nothing(tmp_path):
    """TC1: --help is a question about the tool, never a message to the owner."""
    res, sent = run_notify(tmp_path, "--help")
    assert res.returncode == 0
    assert "notify.sh" in res.stdout
    assert sent == ""


def test_unknown_flag_refused(tmp_path):
    """TC2: a typo'd flag fails loudly instead of going out mangled as text."""
    res, sent = run_notify(tmp_path, "--bogus", "привіт")
    assert res.returncode == 2
    assert "--bogus" in res.stderr
    assert sent == ""


def test_single_dash_text_still_sends(tmp_path):
    """TC3: a message starting with a single dash («-5 градусів») is text, not a flag."""
    res, sent = run_notify(tmp_path, "--no-voice", "--no-stamp", "-5 градусів надворі")
    assert res.returncode == 0
    assert "sendMessage" in sent


def test_double_dash_separator(tmp_path):
    """TC4: `--` ends the flags; what follows is literal text."""
    res, sent = run_notify(tmp_path, "--no-voice", "--no-stamp", "--", "--literal")
    assert res.returncode == 0
    assert "sendMessage" in sent
