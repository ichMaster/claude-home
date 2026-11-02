"""t1113 — the panel's writes must reach the change log, because the panel says they do.

Found by the full review (truth M2): the screen rendered «кожен запис іде в журнал змін» and
`docs/features/ADMIN-PANEL.md` states it as the panel's one hard rule, while `grep changelog
panel/*.py` found exactly one occurrence — a read, on the Pulse screen. The consequence the
doc spells out ("a week later it is still visible who changed what") did not hold for any
panel edit.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import types                                                            # noqa: E402

import changelog_write                                                  # noqa: E402
import prompt_screen                                                    # noqa: E402
import rules_screen                                                     # noqa: E402
import server                                                           # noqa: E402


def read(folder):
    out = []
    for f in sorted(Path(folder).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_a_record_has_the_same_shape_the_hook_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path)
    changelog_write.record("panel-save", "config.local.json", "probes.loe.ttl = 900")
    rec = read(tmp_path)[0]
    assert set(rec) == {"ts", "kind", "target", "detail", "session", "cwd"}
    assert rec["kind"] == "panel-save" and rec["session"] == "panel"


def test_the_log_is_only_appended_to(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path)
    for i in range(3):
        changelog_write.record("panel-save", "x", str(i))
    assert [r["detail"] for r in read(tmp_path)] == ["0", "1", "2"]


def test_an_unwritable_log_never_costs_the_write(tmp_path, monkeypatch):
    """The log is a record, not a gate: if it cannot be written the edit still happens."""
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "file-in-the-way")
    (tmp_path / "file-in-the-way").write_text("не тека", encoding="utf-8")
    changelog_write.record("panel-save", "x", "y")          # must not raise


def test_a_setting_save_is_logged(tmp_path, monkeypatch):
    local = tmp_path / "config.local.json"
    local.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rules_screen, "LOCAL", local)
    monkeypatch.setattr(rules_screen, "_default_config", lambda: {"a": {"b": 1}})
    monkeypatch.setattr(rules_screen, "masked_keys", lambda: [])
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    ok, _ = rules_screen.set_setting("a.b", "2")
    assert ok
    rows = read(tmp_path / "log")
    assert rows and rows[0]["kind"] == "panel-save" and "a.b" in rows[0]["detail"]


def test_a_reset_is_logged(tmp_path, monkeypatch):
    local = tmp_path / "config.local.json"
    local.write_text(json.dumps({"a": {"b": 2}}), encoding="utf-8")
    monkeypatch.setattr(rules_screen, "LOCAL", local)
    monkeypatch.setattr(rules_screen, "_default_config", lambda: {"a": {"b": 1}})
    monkeypatch.setattr(rules_screen, "masked_keys", lambda: [])
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    ok, _ = rules_screen.reset_setting("a.b")
    assert ok and read(tmp_path / "log")[0]["kind"] == "panel-reset"


def test_a_file_save_is_logged(tmp_path, monkeypatch):
    (tmp_path / "persona.md").write_text("я" * 100, encoding="utf-8")
    monkeypatch.setattr(prompt_screen, "HOME", tmp_path)
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    ok, _ = prompt_screen.save_file("persona.md", "я" * 200)
    assert ok
    rec = read(tmp_path / "log")[0]
    assert rec["kind"] == "panel-edit" and "persona.md" in rec["target"]


# --- t1132: the five writes that went past the log --------------------------------------

def _scripts_ok(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: types.SimpleNamespace(
        returncode=0, stdout="ok", stderr=""))


def _scripts_fail(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: types.SimpleNamespace(
        returncode=1, stdout="", stderr="зламалось"))


def test_a_stored_reference_is_logged(tmp_path, monkeypatch):
    """`reference` and `ingest` returned before the record whose own list names them."""
    monkeypatch.setattr(server, "HOME", tmp_path)
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    _scripts_ok(monkeypatch)
    server.zirka_action({"action": ["reference"], "text": ["☽ календар"],
                         "day": ["2026-11-02"], "author": [""]})
    rows = read(tmp_path / "log")
    assert rows and rows[0]["kind"] == "panel-zirka"


def test_an_ingested_file_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "HOME", tmp_path)
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    inbox = tmp_path / "status" / "state" / "astro-reference-inbox"
    inbox.mkdir(parents=True)
    (inbox / "20261102-080000-2026-11-02.txt").write_text("еталон", encoding="utf-8")
    _scripts_ok(monkeypatch)
    server.zirka_action({"action": ["ingest"],
                         "file": ["20261102-080000-2026-11-02.txt"], "day": []})
    rows = read(tmp_path / "log")
    assert rows and rows[0]["kind"] == "panel-zirka"


def test_defer_and_block_are_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    _scripts_ok(monkeypatch)
    server.tasks_action({"action": ["defer"], "id": ["t1"], "when": ["завтра"]})
    server.tasks_action({"action": ["block"], "id": ["t1"], "on": ["on"]})
    rows = read(tmp_path / "log")
    assert len(rows) == 2 and all(r["kind"] == "panel-task" for r in rows)
    assert "defer" in rows[0]["detail"] and "block" in rows[1]["detail"]


def test_pin_change_is_logged(tmp_path, monkeypatch):
    import memory_screen
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    monkeypatch.setattr(memory_screen, "facts", lambda: {
        "in_prompt": [{"id": "f1", "pin": 1}], "cut": [], "unpinned": []})
    _scripts_ok(monkeypatch)
    server.memory_action({"action": ["pin_up"], "id": ["f1"]})
    rows = read(tmp_path / "log")
    assert rows and rows[0]["kind"] == "panel-fact" and "f1" in rows[0]["detail"]


def test_a_failed_script_records_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    _scripts_fail(monkeypatch)
    server.tasks_action({"action": ["defer"], "id": ["t1"], "when": ["завтра"]})
    assert read(tmp_path / "log") == [], "a refusal changed nothing, so it is not a change"


def test_a_refused_write_is_not_logged(tmp_path, monkeypatch):
    local = tmp_path / "config.local.json"
    local.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rules_screen, "LOCAL", local)
    monkeypatch.setattr(rules_screen, "_default_config", lambda: {"a": {"b": 1}})
    monkeypatch.setattr(rules_screen, "masked_keys", lambda: ["a"])
    monkeypatch.setattr(changelog_write, "LOG_DIR", tmp_path / "log")
    assert rules_screen.set_setting("a.b", "2")[0] is False
    assert read(tmp_path / "log") == [], "a refusal changed nothing, so it is not a change"
