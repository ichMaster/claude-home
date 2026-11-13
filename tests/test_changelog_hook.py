"""t1173 — a readonly head must not hide the write behind it.

classify() used to return None whenever READONLY matched the start of the command, so
`cat > f <<EOF`, `tail x > y` and `cat a && rm b` never reached the change log — the daily
summary, /changes and the panel under-reported real changes.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("changelog_hook", ROOT / "changelog" / "hook.py")
hook = importlib.util.module_from_spec(spec)
sys.modules["changelog_hook"] = hook
spec.loader.exec_module(hook)


def bash(cmd):
    return hook.classify({"tool_name": "Bash", "tool_input": {"command": cmd}})


def test_heredoc_write_is_logged():
    """TC1: the common `cat > file <<EOF` idiom is a file creation."""
    res = bash("cat > status/config-patch.json <<EOF\n{}\nEOF")
    assert res is not None and res[0] == "bash"


def test_redirect_after_read_is_logged():
    """TC2: a read piped into a file is a write."""
    assert bash("tail -100 app.log > /tmp/out.txt") is not None


def test_compound_rm_after_read_is_logged():
    """TC2: the rm after && must not hide behind the cat."""
    res = bash("cat a.txt && rm old.txt")
    assert res is not None
    assert "rm" in res[1]


def test_multiline_second_line_mutation_is_logged():
    """TC3: only the first line used to decide."""
    assert bash("cat a.txt\nrm old.txt") is not None


def test_pure_reads_stay_unlogged():
    """TC4: the suppression still works where it should."""
    for cmd in ("cat a.txt", "git status", "git log --oneline -5",
                "systemctl --user status noos-digest.timer", "sed -n '1,10p' f.py",
                "grep -rn pattern src/"):
        assert bash(cmd) is None, cmd


def test_plain_mutation_still_logged_with_verb():
    """TC5: nothing regressed for the simple case."""
    res = bash("rm -rf build")
    assert res is not None and res[1] == "rm"
