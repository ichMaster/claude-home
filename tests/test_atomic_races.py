"""t1104 — the atomic write under threads, and a version copy that cannot lie.

The panel is a ThreadingHTTPServer: every request is a thread of one process, so four writers
share `os.getpid()`. Found by the full review (H1): two writes to one file left
`config.local.json` unparseable in half the trials and `CLAUDE.md` a hybrid of two bodies —
`os.replace` is atomic, but the file it was handed was not.
"""
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import noosconf                                                         # noqa: E402

BIG = {"probes": {"youtube": {"channels": [{"name": f"c{i}"} for i in range(600)]}},
       "user": {"name": "хтось"}}


def test_two_threads_writing_one_file_never_tear_it(tmp_path, monkeypatch):
    """The regression: the file must always parse, and no write may raise."""
    monkeypatch.setattr(noosconf, "precious", lambda target: False)
    target = tmp_path / "config.local.json"
    target.write_text(json.dumps(BIG, ensure_ascii=False), encoding="utf-8")
    errors, bodies = [], [json.dumps(BIG | {"a": i}, ensure_ascii=False) * 3
                         for i in range(2)]

    def write(i):
        try:
            noosconf.atomic_write_text(target, bodies[i])
        except Exception as exc:                                        # noqa: BLE001
            errors.append(repr(exc))

    for _ in range(20):
        threads = [threading.Thread(target=write, args=(i,)) for i in (0, 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        got = target.read_text(encoding="utf-8")
        assert got in bodies, "the file must be one of the two bodies, never a weld of both"
    assert errors == [], errors


def test_the_lock_serialises_a_read_modify_write(tmp_path):
    """Unique temp files stop the tearing; the lock is what stops a lost update — two
    writers that each read, change one key and write back must both survive."""
    target = tmp_path / "doc.json"
    target.write_text("{}", encoding="utf-8")

    def bump(key):
        for _ in range(40):
            with noosconf.locked(target):
                blob = json.loads(target.read_text(encoding="utf-8"))
                blob[key] = blob.get(key, 0) + 1
                target.write_text(json.dumps(blob), encoding="utf-8")

    threads = [threading.Thread(target=bump, args=(k,)) for k in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 40, "b": 40}


def test_the_temp_file_is_not_named_by_the_pid(tmp_path, monkeypatch):
    """The actual defect: one name for every thread of the process."""
    monkeypatch.setattr(noosconf, "precious", lambda target: False)
    seen = []
    target = tmp_path / "x.json"
    real_replace = noosconf.os.replace

    def spy(src, dst):
        seen.append(Path(src).name)
        real_replace(src, dst)
    monkeypatch.setattr(noosconf.os, "replace", spy)
    noosconf.atomic_write_text(target, "1")
    noosconf.atomic_write_text(target, "2")
    assert len(set(seen)) == 2, "each write needs its own temp file"


def test_a_version_that_could_not_be_kept_is_reported(tmp_path, monkeypatch):
    """M6: `keep_version` swallowed every failure, so a save could promise a copy that was
    never taken — and `versions.dir` is editable from the form, which is how it breaks."""
    target = tmp_path / "persona.md"
    target.write_text("перед", encoding="utf-8")
    monkeypatch.setattr(noosconf, "precious", lambda t: True)
    monkeypatch.setattr(noosconf, "_versions_root",
                        lambda: tmp_path / "nowhere" / "deep")
    (tmp_path / "nowhere").write_text("не тека", encoding="utf-8")   # a file in the way
    assert noosconf.keep_version(target) is None
    assert noosconf.version_failed(target), \
        "the caller must be able to find out that no copy was taken"
    noosconf.atomic_write_text(target, "після")
    assert target.read_text(encoding="utf-8") == "після", \
        "losing a version must still never cost the write"
