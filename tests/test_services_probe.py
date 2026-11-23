"""t1208 — the services probe ran `docker ps` as a bare assignment under
`set -euo pipefail`, so a stopped docker daemon killed the script before any JSON was
printed. run.sh then substituted the generic one-shot fallback, which silenced the
repeating tmux-dead alert for as long as docker stayed down."""
import json
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "status" / "probes" / "services.sh"


def _stub(bindir: Path, name: str, body: str):
    p = bindir / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def _run(bindir: Path):
    env = dict(os.environ, PATH=f"{bindir}:/usr/bin:/bin")
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)


def _healthy_stubs(bindir: Path, docker_body: str, tmux_ok: bool = True):
    _stub(bindir, "docker", docker_body)
    _stub(bindir, "tmux", "exit 0" if tmux_ok else "exit 1")
    _stub(bindir, "systemctl", 'echo active')


def test_wedged_docker_still_emits_json(tmp_path):
    """t1247 TC1: a daemon that hangs (not errors) is bounded and named, not a stalled run."""
    _healthy_stubs(tmp_path, "sleep 30")
    env = dict(os.environ, PATH=f"{tmp_path}:/usr/bin:/bin", SERVICES_DOCKER_TIMEOUT="1")
    out = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                         env=env, timeout=10)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["severity"] == "warn"
    assert "docker" in data["text"]
    assert data["value"]["tmux"] is True


def test_dead_docker_still_emits_json(tmp_path):
    """TC1: a stopped daemon must be a named warn, not a dead probe."""
    _healthy_stubs(tmp_path, 'echo "Cannot connect to the Docker daemon" >&2; exit 1')
    out = _run(tmp_path)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["id"] == "services"
    assert data["severity"] == "warn"
    assert "docker" in data["text"]
    assert data["value"]["tmux"] is True


def test_dead_docker_does_not_silence_the_tmux_alert(tmp_path):
    """TC2: the dead-session alert survives an unrelated docker outage."""
    _healthy_stubs(tmp_path, "exit 1", tmux_ok=False)
    out = _run(tmp_path)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["severity"] == "alert"
    assert "tmux" in data["text"]


def test_healthy_docker_unchanged(tmp_path):
    """TC3: the happy path keeps its shape — containers counted, severity info."""
    _healthy_stubs(
        tmp_path,
        'if [ "$1" = "ps" ] && [ "${2:-}" = "-q" ]; then printf "a\\nb\\n"; fi',
    )
    out = _run(tmp_path)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["ok"] is True
    assert data["severity"] == "info"
    assert data["value"]["containers"] == 2
