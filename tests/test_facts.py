"""t1081 — memory/facts.py is loadable as a module without its CLI firing.

The panel (`panel/memory_screen.py`) executes the file by path to borrow `load()`; an
unguarded dispatch meant every /memory view printed the whole fact store — address, birth
data — into the panel's journal.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv-voice" / "bin" / "python")
FACTS = str(ROOT / "memory" / "facts.py")

sys.path.insert(0, str(ROOT / "panel"))

import memory_screen                                                     # noqa: E402


def test_loading_the_module_prints_nothing(monkeypatch, capsys):
    """t1081 TC1/TC2 — loading the way the panel does runs no command and prints nothing."""
    monkeypatch.setattr(sys, "argv", ["panel/server.py"])
    mod = memory_screen._facts_module()
    assert capsys.readouterr().out == "", "the CLI dispatch ran on module load"
    assert callable(mod.load) and callable(mod.prompt)


def test_the_cli_still_answers():
    """t1081 TC3 — run as a script, the dispatch still works (start.sh depends on it)."""
    out = subprocess.run([PY, FACTS, "prompt"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0
