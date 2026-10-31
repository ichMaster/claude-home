"""t1052 — after a fresh start, an in-process claude exit must restart WITH --continue:
the one-shot .fresh flag applies to the first iteration only, not to every crash after it."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_restart_recontinues_after_fresh_start(tmp_path):
    home = tmp_path
    ch = home / "claude-home"
    proj = home / ".claude" / "projects" / "-home-ich-claude-home"
    lbin = home / ".local" / "bin"
    vbin = ch / ".venv-voice" / "bin"
    for d in (ch, proj, lbin, vbin):
        d.mkdir(parents=True)
    (ch / "persona.md").write_text("persona")
    (ch / ".fresh").touch()
    (vbin / "python").write_text("#!/bin/sh\nexit 0\n")
    log = home / "args.log"
    # the stub records each invocation's args, leaves a transcript behind (a real session
    # would), and stops the restart loop after the second run
    (lbin / "claude").write_text(
        "#!/bin/sh\n"
        # one log line per invocation: the prompt argument holds newlines, so a bare echo
        # would split one run across lines and break the run count
        f'printf \'%s \' "$@" | tr \'\\n\' \' \' >> "{log}"\n'
        f'printf \'\\n\' >> "{log}"\n'
        f'touch "{proj}/t.jsonl"\n'
        f'[ "$(wc -l < "{log}")" -ge 2 ] && kill $PPID\n'
        "exit 0\n")
    for f in (vbin / "python", lbin / "claude"):
        f.chmod(0o755)

    subprocess.run(["bash", str(ROOT / "start.sh")], check=False, timeout=30,
                   capture_output=True,
                   env={"HOME": str(home), "NOOS_RESTART_DELAY": "0",
                        "PATH": os.environ.get("PATH", "/usr/bin:/bin")})

    runs = log.read_text().splitlines()
    assert len(runs) >= 2, f"expected two claude runs, got {runs}"
    assert "--continue" not in runs[0], "fresh start must not continue"
    assert "--continue" in runs[1], "restart after a fresh start must continue the conversation"


def test_start_sh_parses():
    subprocess.run(["bash", "-n", str(ROOT / "start.sh")], check=True)
