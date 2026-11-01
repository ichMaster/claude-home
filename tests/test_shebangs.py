"""t1117 — a script the documentation tells a person to run must actually run.

Found by the owner, 2026-11-01: `./panel/auth.py` answered
`/usr/bin/env: ‘python’: No such file or directory`. This machine has `python3` only; every
script in the project carried `#!/usr/bin/env python`, which never mattered because the
timers and the session invoke them as `.venv-voice/bin/python <script>` — except the handful
the docs hand to a human as `./something.py`, which is the only way to set the panel's
password.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The scripts the documentation tells a person to run directly. Each is stdlib-only (plus
# `noosconf`, itself stdlib), so the system interpreter is enough — anything needing the
# venv's packages stays a `.venv-voice/bin/python …` command and is not listed here.
DIRECT = ["panel/auth.py", "tools/permissions.py", "tools/versions.py"]


@pytest.mark.parametrize("name", DIRECT)
def test_the_shebang_resolves_on_this_machine(name):
    line = (ROOT / name).read_text(encoding="utf-8").splitlines()[0]
    assert line.startswith("#!"), name
    interpreter = line[2:].split()[0]
    if interpreter.endswith("env"):
        wanted = line[2:].split()[1]
        assert shutil.which(wanted), f"{name}: no «{wanted}» on PATH"
    else:
        assert Path(interpreter).exists(), name


@pytest.mark.parametrize("name", DIRECT)
def test_the_script_is_executable(name):
    import os
    assert os.access(ROOT / name, os.X_OK), f"{name} is documented as ./{name}"


@pytest.mark.parametrize("name", DIRECT)
def test_running_it_through_its_own_shebang_works(name):
    """Not just the shebang: the imports have to be satisfiable by that interpreter too."""
    out = subprocess.run([str(ROOT / name)], capture_output=True, text=True, timeout=60,
                         cwd=str(ROOT))
    assert "No such file or directory" not in (out.stderr or ""), out.stderr
    assert "ModuleNotFoundError" not in (out.stderr or ""), out.stderr
    assert "Traceback" not in (out.stderr or ""), out.stderr


def test_the_rest_still_run_under_the_project_interpreter():
    """The other scripts keep their shebang: they need the venv's packages, and a shebang
    cannot point at a relative path. They are always invoked explicitly."""
    out = subprocess.run([str(ROOT / ".venv-voice" / "bin" / "python"),
                          str(ROOT / "memory" / "facts.py"), "list"],
                         capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
