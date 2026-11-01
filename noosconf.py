"""Shared configuration loader.

`config.json` holds neutral defaults and is committed; `config.local.json` holds
machine- and person-specific values and is git-ignored. The local file is merged
on top, key by key, so it only needs to carry what differs.

    from noosconf import conf, path
    conf("memory.max_facts", 100)
    path("memory.db")            # absolute Path, resolved against the repo root
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _merge(base, over):
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _load():
    data = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"
    if local.exists():
        _merge(data, json.loads(local.read_text(encoding="utf-8")))
    return data


DATA = _load()
_CHECKED = 0.0                 # when the files were last stat-ed
_STAMPS = None                 # their (mtime, size) pairs at the last load
# How long a loaded configuration is trusted without a stat. This used to be forever: `DATA`
# was an import-time snapshot, and the panel is a process that lives for weeks and now
# writes configuration itself — so three screens kept stating the value the file held when
# the panel started, including the channel toggle that writes the file it was reading
# (t1109). A stat is cheap; a stat per `conf()` call in a request loop is not.
FRESH_FOR = 2.0


def _stamps():
    # ROOT is part of the key: a test (or a tool) that repoints it must get its own files
    # read immediately rather than inheriting the previous load.
    out = [str(ROOT)]
    for name in ("config.json", "config.local.json"):
        try:
            st = (ROOT / name).stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def _refresh():
    """Re-read the configuration when the files have changed. Never leaves a running process
    without a configuration: a half-written file keeps the last good one."""
    global DATA, _CHECKED, _STAMPS
    import time
    now = time.monotonic()
    if now - _CHECKED < FRESH_FOR:
        return
    _CHECKED = now
    stamps = _stamps()
    if _STAMPS is None:
        _STAMPS = stamps
        return
    if stamps == _STAMPS:
        return
    if stamps[0] != _STAMPS[0]:
        _CHECKED = 0.0                      # a different ROOT: do not cache this decision
    try:
        DATA = _load()
        _STAMPS = stamps
    except (OSError, json.JSONDecodeError, ValueError):
        pass                   # a torn write mid-save: keep what we have and try later


def reload():
    """Force a re-read now — for a caller that has just written a config file itself."""
    global _CHECKED, _STAMPS
    _CHECKED, _STAMPS = 0.0, None
    try:
        globals()["DATA"] = _load()
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    _STAMPS = _stamps()


def conf(dotted, default=None):
    """conf("probes.loe.queue") -> value, or `default` if the key is absent."""
    _refresh()
    node = DATA
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


FAILED_VERSIONS = set()          # targets whose last version copy did not happen


def locked(target):
    """A lock on one file, held across a read-modify-write.

    The unique temp file below stops a torn file; this stops a *lost update*, which is the
    other half of the same race: two callers that each read, change one key and write back
    would otherwise keep only the last read's view. `flock` is held on a sidecar, so it
    works between threads and between processes — the panel, the CLI tools and the timers
    all write these files.
    """
    return _FileLock(Path(target))


class _FileLock:
    def __init__(self, target):
        self.path = target.with_name(f".{target.name}.lock")
        self.handle = None

    def __enter__(self):
        import fcntl
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(self.path, "a+")
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            self.handle = None          # an unlockable directory must not block the write
        return self

    def __exit__(self, *exc):
        if self.handle:
            import fcntl
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
        return False


def version_failed(target) -> bool:
    """Did the last `keep_version` for this target fail? The write still happens — losing a
    version must never cost the write it was protecting — but the caller has to be able to
    stop promising a copy that was never taken (t1104)."""
    try:
        return str(Path(target).resolve()) in FAILED_VERSIONS
    except OSError:
        return False


def atomic_write_text(target, text, encoding="utf-8"):
    """Write via a temp file in the same directory + os.replace, so a crash mid-write can
    never leave the target torn. Keeps the target's permissions (config.local.json is 600).

    The temp file gets a **unique** name. It used to be `name.tmp<pid>`, which is one name
    for every thread of a process — and the panel is a threading server, so two saves of one
    file interleaved inside a single temp and one thread's cleanup deleted the other's file
    before it was renamed. Half the trials left `config.local.json` unparseable (t1104).
    `os.replace` is atomic; the file it is handed has to be, too.

    Atomicity is not a backup (the owner, 2026-11-01): it protects against a write cut in
    half, not against a correct write of the wrong content, an `rm`, or a dead disk. The
    previous content is kept by `keep_version()` for the files where losing it hurts; when
    that copy could not be taken, `version_failed()` says so.
    """
    import tempfile
    target = Path(target)
    keep_version(target)
    mode = target.stat().st_mode & 0o7777 if target.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent),
                                    prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        os.chmod(tmp, mode if mode is not None else 0o600)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


# --- versions ------------------------------------------------------------------------------

def _versions_root():
    return Path(conf("versions.dir", str(ROOT / ".versions"))).expanduser()


def precious(target) -> bool:
    """Is this a file whose previous content is worth keeping?

    Not "everything that gets rewritten". `status/state/youtube.json` is 68 KB rewritten
    on every poll with a new cursor and timestamp, and the bots' state is 24 KB every two
    minutes: versioning those would be ten megabytes a day of copied cursors, and the one
    config the whole thing exists to protect would be lost in the pile. What is listed in
    `versions.files` is what actually hurts to lose — birth data and the channel list,
    the pinned facts, the YouTube refresh token, the memory of what was already sent.
    Caches and cursors rebuild themselves and are deliberately absent (2026-11-01).
    """
    try:
        target = Path(target).resolve()
    except OSError:
        return False
    for rel in conf("versions.files", []) or []:
        p = Path(str(rel)).expanduser()
        if not p.is_absolute():
            p = ROOT / p
        try:
            p = p.resolve()
        except OSError:
            continue
        if target == p or p in target.parents:
            return True
    return False


def keep_version(target) -> "Path | None":
    """Copy the current content aside before it is replaced. Returns the copy, or None.

    Three rules, each one a correction to the naive form:

    * only files on the precious list — see `precious()`;
    * **nothing is written when the content has not changed.** Most rewrites here are
      identical to what is already on disk, and a copy per write would bury the real
      changes under hundreds of duplicates;
    * a cap on how many copies a file keeps (`versions.keep`). That is a safety belt, not
      a retention policy — thinning by age belongs to the proper backup, which is its own
      phase.

    Never raises: losing a version must never cost the write it was protecting.
    """
    try:
        target = Path(target)
        if not target.is_file() or not precious(target):
            FAILED_VERSIONS.discard(str(target.resolve()))
            return None
        blob = target.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()[:16]
        try:
            rel = target.resolve().relative_to(ROOT)
        except ValueError:
            rel = Path(target.name)
        folder = _versions_root() / rel.parent / rel.name
        folder.mkdir(parents=True, exist_ok=True)
        kept = sorted(folder.glob("*.bin"))
        if kept and kept[-1].name.endswith(f".{digest}.bin"):
            return None                        # unchanged since the last version
        # microseconds, not seconds: several writes inside one second are normal here
        # (a restore versions the file it replaces), and a colliding name would quietly
        # overwrite the older copy — losing exactly the version being protected
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        copy = folder / f"{stamp}.{digest}.bin"
        copy.write_bytes(blob)
        os.chmod(copy, target.stat().st_mode & 0o7777)
        keep = int(conf("versions.keep", 40))
        for old in kept[:max(0, len(kept) + 1 - keep)]:
            old.unlink(missing_ok=True)
        FAILED_VERSIONS.discard(str(target.resolve()))
        return copy
    except Exception:                          # noqa: BLE001 — a version is never worth a write
        # ...but silence about it is: `versions.dir` is editable from the panel's form, so a
        # wrong value made every «копія лишилась» message a promise nobody kept (t1104, M6).
        try:
            FAILED_VERSIONS.add(str(Path(target).resolve()))
        except OSError:
            pass
        return None


def path(dotted, default=None):
    """Same as conf(), but returns an absolute Path (~ expanded, relative to ROOT)."""
    value = conf(dotted, default)
    if value is None:
        return None
    p = Path(os.path.expanduser(str(value)))
    return p if p.is_absolute() else ROOT / p
