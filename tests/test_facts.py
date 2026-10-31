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


# --- t1082 — rm/pin must not leave the facts directory --------------------------------

def run_cli(*args):
    return subprocess.run([PY, FACTS, *args], capture_output=True, text=True, timeout=60)


def hops_to(p: Path) -> str:
    """A traversal id: enough `..` to reach / from the facts dir, then the target."""
    return "/".join([".."] * 12) + str(p)


def test_rm_cannot_leave_the_facts_directory(tmp_path):
    """t1082 TC1 — the id arrives from the panel's unauthenticated form; before the fix
    this deleted the victim and exited 0."""
    victim = tmp_path / "victim.md"
    victim.write_text("не факт", encoding="utf-8")
    out = run_cli("rm", hops_to(tmp_path / "victim"))
    assert victim.exists(), "a traversal id deleted a file outside memory/facts"
    assert out.returncode != 0


def test_pin_cannot_leave_the_facts_directory(tmp_path):
    """t1082 TC2 — same hole: pin rewrote the pin line of an arbitrary .md."""
    victim = tmp_path / "victim.md"
    victim.write_text("---\npin: 1\n---\nтекст\n", encoding="utf-8")
    out = run_cli("pin", hops_to(tmp_path / "victim"), "2")
    assert victim.read_text(encoding="utf-8").startswith("---\npin: 1")
    assert out.returncode != 0


def test_fact_file_keeps_ids_inside_the_directory():
    """t1082 TC3."""
    mod = memory_screen._facts_module()
    assert mod.fact_file("../escape") is None
    assert mod.fact_file("a/b") is None
    got = mod.fact_file("plain-id")
    assert got is not None and got.name == "plain-id.md"


def test_rm_of_a_missing_fact_is_a_clean_refusal():
    """t1082 TC4 — a message and exit 1, not a traceback."""
    out = run_cli("rm", "no-such-fact-xyz")
    assert out.returncode != 0
    assert "Traceback" not in (out.stderr or "")


# --- t1083 — pin goes through the versioned atomic write -------------------------------

def test_repin_keeps_a_version_and_the_text(monkeypatch, tmp_path):
    """t1083 TC1/TC2 — a fact file is precious (t1080); repinning must keep the
    pre-change content as a version and touch only the pin line. Before the fix the
    rewrite was a raw write_text: no version, tearable."""
    import noosconf
    root = tmp_path / "repo"
    (root / "facts").mkdir(parents=True)
    store = tmp_path / "versions"
    monkeypatch.setattr(noosconf, "ROOT", root)
    real_conf = noosconf.conf

    def fake(key, default=None):
        if key == "versions.dir":
            return str(store)
        if key == "versions.files":
            return ["facts"]
        return real_conf(key, default)
    monkeypatch.setattr(noosconf, "conf", fake)

    f = root / "facts" / "one.md"
    f.write_text("---\npin: 1\ntags: \nadded: 2026-11-01\n---\nважливий текст\n",
                 encoding="utf-8")
    memory_screen._facts_module().set_pin(f, "2")

    got = f.read_text(encoding="utf-8")
    assert "pin: 2" in got and "важливий текст" in got
    copies = list(store.rglob("*.bin"))
    assert len(copies) == 1, "the pre-change content must be kept as a version"
    assert "pin: 1" in copies[0].read_text(encoding="utf-8")
