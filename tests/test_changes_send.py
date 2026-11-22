"""t1234 — changes-send.sh must not swallow a crashed collector as a quiet day.

The script runs against a fake $HOME: a copy of changes-send.sh, a stub venv python
(execs the real python3), a scenario-controlled stub probe and a stub notify.sh that
logs its argv — nothing real is ever sent, even while the test is red.
"""
import os
import stat
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fake_home(tmp_path, probe_body):
    home = tmp_path / "home"
    ch = home / "claude-home"
    (ch / "status" / "probes").mkdir(parents=True)
    (ch / "tools").mkdir()
    shutil.copy2(ROOT / "status" / "changes-send.sh", ch / "status" / "changes-send.sh")

    vbin = ch / ".venv-voice" / "bin"
    vbin.mkdir(parents=True)
    py = vbin / "python"
    py.write_text(f"#!/usr/bin/env bash\nexec {sys.executable} \"$@\"\n")
    py.chmod(py.stat().st_mode | stat.S_IXUSR)

    (ch / "tools" / "versions.py").write_text("pass\n")
    (ch / "status" / "probes" / "changes.py").write_text(probe_body)

    log = tmp_path / "notify.log"
    notify = ch / "notify.sh"
    notify.write_text("#!/usr/bin/env bash\n" f"echo \"$@\" >> {log}\n")
    notify.chmod(notify.stat().st_mode | stat.S_IXUSR)
    return home, ch, log


def run_send(tmp_path, probe_body):
    home, ch, log = fake_home(tmp_path, probe_body)
    env = dict(os.environ, HOME=str(home))
    res = subprocess.run([str(ch / "status" / "changes-send.sh")],
                         capture_output=True, text=True, env=env, timeout=60)
    sent = log.read_text() if log.exists() else ""
    return res, sent


def test_crashed_collector_warns_and_fails(tmp_path):
    """t1234 TC1: a non-zero changes.py is a reported failure, not a quiet day."""
    res, sent = run_send(tmp_path, "import sys; sys.exit(3)\n")
    assert res.returncode == 1
    assert "⚠️" in sent


def test_non_json_output_warns_and_fails(tmp_path):
    """t1234 TC2: unparseable collector output is a reported failure."""
    res, sent = run_send(tmp_path, "print('Traceback (most recent call last):')\n")
    assert res.returncode == 1
    assert "⚠️" in sent


def test_good_summary_is_sent(tmp_path):
    """t1234 TC3: the happy path still sends the summary."""
    res, sent = run_send(tmp_path, "import json; print(json.dumps({'text': 'щось'}))\n")
    assert res.returncode == 0
    assert "📝 щось" in sent


def test_quiet_day_stays_quiet(tmp_path):
    """t1234 TC4: empty text from a healthy collector sends nothing, exit 0."""
    res, sent = run_send(tmp_path, "import json; print(json.dumps({'text': ''}))\n")
    assert res.returncode == 0
    assert sent == ""
