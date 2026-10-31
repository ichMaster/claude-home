"""t1080 — the previous content of a file that matters is kept beside it.

The owner's point (2026-11-01): the atomic write protects against a torn write, not
against a correct write of the wrong thing. These tests are mostly about the three
corrections that keep the idea usable — only precious files, nothing written when nothing
changed, and a cap so a runaway writer cannot fill the disk.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import noosconf                                                         # noqa: E402

_spec = importlib.util.spec_from_file_location("noos_versions",
                                               ROOT / "tools" / "versions.py")
versions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(versions)


def sandbox(monkeypatch, tmp_path, files=("precious.json",), keep=40):
    """Point the repo root, the versions dir and the precious list at tmp_path."""
    root = tmp_path / "repo"
    root.mkdir()
    store = tmp_path / "versions"
    monkeypatch.setattr(noosconf, "ROOT", root)
    monkeypatch.setattr(versions, "ROOT", root)
    real_conf = noosconf.conf

    def fake(key, default=None):
        if key == "versions.dir":
            return str(store)
        if key == "versions.files":
            return list(files)
        if key == "versions.keep":
            return keep
        return real_conf(key, default)
    monkeypatch.setattr(noosconf, "conf", fake)
    monkeypatch.setattr(versions, "conf", fake)
    return root


def test_version_is_kept_before_a_rewrite(monkeypatch, tmp_path):
    root = sandbox(monkeypatch, tmp_path)
    f = root / "precious.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    noosconf.atomic_write_text(f, '{"a": 2}')
    assert f.read_text(encoding="utf-8") == '{"a": 2}'
    kept = versions.versions(f)
    assert len(kept) == 1
    assert kept[0]["file"].read_text(encoding="utf-8") == '{"a": 1}', "the OLD content"


def test_unchanged_content_makes_no_new_version(monkeypatch, tmp_path):
    """The correction that matters most: most rewrites here are identical, and a copy per
    write would bury the real changes under hundreds of duplicates."""
    root = sandbox(monkeypatch, tmp_path)
    f = root / "precious.json"
    f.write_text("v1", encoding="utf-8")

    # A version holds what was on disk BEFORE the write. Five identical rewrites therefore
    # produce exactly one — the first takes a copy of "v1", the rest find nothing new.
    for _ in range(5):
        noosconf.atomic_write_text(f, "v1")
    assert len(versions.versions(f)) == 1
    assert versions.versions(f)[0]["file"].read_text(encoding="utf-8") == "v1"

    # Writing something different still adds nothing yet: what is on disk at that moment
    # is still "v1", already kept. "v2" becomes a version only when it is itself replaced.
    noosconf.atomic_write_text(f, "v2")
    assert len(versions.versions(f)) == 1
    noosconf.atomic_write_text(f, "v3")
    bodies = [v["file"].read_text(encoding="utf-8") for v in versions.versions(f)]
    assert bodies == ["v2", "v1"], "newest first, each the content it replaced"


def test_a_cache_is_not_versioned(monkeypatch, tmp_path):
    """A cursor rewritten every poll is deliberately absent from the list."""
    root = sandbox(monkeypatch, tmp_path)
    cache = root / "cache.json"
    cache.write_text("1", encoding="utf-8")
    noosconf.atomic_write_text(cache, "2")
    assert versions.versions(cache) == []


def test_a_directory_on_the_list_covers_its_files(monkeypatch, tmp_path):
    root = sandbox(monkeypatch, tmp_path, files=("facts",))
    (root / "facts").mkdir()
    f = root / "facts" / "one.md"
    f.write_text("старий факт", encoding="utf-8")
    noosconf.atomic_write_text(f, "новий факт")
    assert len(versions.versions(f)) == 1


def test_cap_is_a_safety_belt(monkeypatch, tmp_path):
    """Not a retention policy — thinning by age is the proper backup's job (phase 10) —
    but a runaway writer must not fill the disk overnight."""
    root = sandbox(monkeypatch, tmp_path, keep=3)
    f = root / "precious.json"
    f.write_text("v0", encoding="utf-8")
    for i in range(1, 8):
        noosconf.atomic_write_text(f, f"v{i}")
    kept = versions.versions(f)
    assert len(kept) == 3
    bodies = [v["file"].read_text(encoding="utf-8") for v in kept]
    assert bodies == ["v6", "v5", "v4"], "the newest are the ones kept"


def test_a_version_failure_never_costs_the_write(monkeypatch, tmp_path):
    root = sandbox(monkeypatch, tmp_path)
    f = root / "precious.json"
    f.write_text("before", encoding="utf-8")

    def boom(*a, **k):
        raise OSError("versions dir is gone")
    monkeypatch.setattr(noosconf, "_versions_root", boom)
    noosconf.atomic_write_text(f, "after")
    assert f.read_text(encoding="utf-8") == "after", "the write must still land"


def test_diff_and_restore_round_trip(monkeypatch, tmp_path):
    root = sandbox(monkeypatch, tmp_path)
    f = root / "precious.json"
    f.write_text(json.dumps({"канали": 603}, ensure_ascii=False), encoding="utf-8")
    noosconf.atomic_write_text(f, json.dumps({"канали": 0}, ensure_ascii=False))

    v = versions.versions(f)[0]
    d = versions.diff_text(f, v)
    assert "603" in d and "0" in d

    versions.restore(f, v)
    assert json.loads(f.read_text(encoding="utf-8"))["канали"] == 603
    assert len(versions.versions(f)) == 2, "restoring also versions what it replaced"

    # and the undo can be undone
    versions.restore(f, versions.versions(f)[0])
    assert json.loads(f.read_text(encoding="utf-8"))["канали"] == 0


def test_permissions_are_carried_to_the_copy(monkeypatch, tmp_path):
    """config.local.json is 600 and holds birth data; its copy must not be readable by
    anyone the original is not."""
    root = sandbox(monkeypatch, tmp_path)
    f = root / "precious.json"
    f.write_text("секрет", encoding="utf-8")
    f.chmod(0o600)
    noosconf.atomic_write_text(f, "інше")
    assert versions.versions(f)[0]["file"].stat().st_mode & 0o777 == 0o600


def test_listing_an_untracked_file_says_why(monkeypatch, tmp_path, capsys):
    root = sandbox(monkeypatch, tmp_path)
    cache = root / "cache.json"
    cache.write_text("1", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["versions.py", "list", str(cache)])
    versions.main()
    assert "versions.files" in capsys.readouterr().out
