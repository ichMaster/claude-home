"""t1142 — the nightly review must be waited for, and a run that produced no report must fail.

Eight consecutive nights (3-10 November 2026) the review session was terminated at the
`claude -p` background-task ceiling of 600 s, mid fan-out, so no scan report was ever
written — and because the script ended in `exec claude`, systemd recorded every one of those
nights as a clean success. Both halves are regressions here: the ceiling is lifted, and a
missing report is a loud failure.
"""
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "status" / "code-review-headless.sh"


def test_script_parses():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_background_ceiling_lifted():
    """TC1 — the ceiling is raised before claude is invoked, not left at its 600 s default."""
    text = SCRIPT.read_text()
    m = re.search(r"^\s*export\s+CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=(\S+)", text, re.M)
    assert m, "no CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS export — the review dies at 600 s"
    assert m.group(1).strip('"') == "0", "0 means wait indefinitely; the unit's timeout bounds the run"
    call = re.search(r"^claude -p", text, re.M)
    assert call, "the session is no longer started by a plain `claude -p` line"
    assert m.start() < call.start(), "the export must precede the session"


def test_session_is_not_exec():
    """TC2 — exec would replace the shell, leaving no room for the post-run check."""
    assert not re.search(r"^\s*exec\s+claude\b", SCRIPT.read_text(), re.M)


# --- end to end, with stubs for claude, notify.sh and the venv python -------------------

def _home(tmp_path, write_report):
    """A throwaway $HOME/claude-home holding the real script and stubs for everything else."""
    home = tmp_path / "home"
    repo = home / "claude-home"
    (repo / "status" / "state" / "code-review").mkdir(parents=True)
    (repo / ".venv-voice" / "bin").mkdir(parents=True)
    (repo / "bin").mkdir()

    (repo / "status" / "code-review-headless.sh").write_bytes(SCRIPT.read_bytes())
    (repo / "status" / "code-review-headless.sh").chmod(0o755)
    (repo / "status" / "code-review-prompt.md").write_text("review the repository\n")
    (repo / "status" / "digest-settings.json").write_text(json.dumps({"enabledPlugins": {}}))

    python = repo / ".venv-voice" / "bin" / "python"
    python.write_text('#!/usr/bin/env bash\necho claude-fable-5\n')
    python.chmod(0o755)

    notify = repo / "notify.sh"
    notify.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$HOME/claude-home/status/state/notify.log"\n'
    )
    notify.chmod(0o755)

    claude = repo / "bin" / "claude"
    body = '#!/usr/bin/env bash\n'
    if write_report:
        body += (
            'd="$HOME/claude-home/status/state/code-review"\n'
            'printf "verdict: clean\\n" > "$d/$(date +%F)-scan.md"\n'
        )
    body += 'exit 0\n'
    claude.write_text(body)
    claude.chmod(0o755)
    return home, repo


def _run(home, repo):
    env = dict(os.environ, HOME=str(home), PATH=f"{repo / 'bin'}:{os.environ['PATH']}")
    env.pop("NOOS_SENT_KIND", None)
    return subprocess.run(
        ["bash", str(repo / "status" / "code-review-headless.sh")],
        env=env, capture_output=True, text=True, timeout=60,
    )


def _notified(repo):
    log = repo / "status" / "state" / "notify.log"
    return log.read_text().splitlines() if log.exists() else []


def test_report_written_is_success(tmp_path):
    """TC3 — a review that wrote today's scan report succeeds quietly."""
    home, repo = _home(tmp_path, write_report=True)
    res = _run(home, repo)
    assert res.returncode == 0, res.stderr
    assert _notified(repo) == [], "nothing to warn about when the report is there"


def test_missing_report_fails_loudly(tmp_path):
    """TC4 — no report means the unit must show failed, and one warning goes out."""
    home, repo = _home(tmp_path, write_report=False)
    res = _run(home, repo)
    assert res.returncode != 0, "a silent success is what hid eight broken nights"
    assert len(_notified(repo)) == 1, _notified(repo)


def test_warning_is_quiet(tmp_path):
    """TC5 — it arrives around five in the morning."""
    home, repo = _home(tmp_path, write_report=False)
    _run(home, repo)
    assert "--quiet" in _notified(repo)[0]


def test_yesterdays_report_does_not_count(tmp_path):
    """TC6 — only a report dated today proves this run produced anything."""
    home, repo = _home(tmp_path, write_report=False)
    stale = datetime.date.today() - datetime.timedelta(days=1)
    (repo / "status" / "state" / "code-review" / f"{stale}-scan.md").write_text("old\n")
    res = _run(home, repo)
    assert res.returncode != 0
    assert len(_notified(repo)) == 1
