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


def conf(dotted, default=None):
    """conf("probes.loe.queue") -> value, or `default` if the key is absent."""
    node = DATA
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def atomic_write_text(target, text, encoding="utf-8"):
    """Write via a temp file in the same directory + os.replace, so a crash mid-write can
    never leave the target torn. Keeps the target's permissions (config.local.json is 600).

    Atomicity is not a backup (the owner, 2026-11-01): it protects against a write cut in
    half, not against a correct write of the wrong content, an `rm`, or a dead disk. The
    previous content is kept by `keep_version()` for the files where losing it hurts.
    """
    target = Path(target)
    keep_version(target)
    tmp = target.with_name(f"{target.name}.tmp{os.getpid()}")
    try:
        tmp.write_text(text, encoding=encoding)
        if target.exists():
            os.chmod(tmp, target.stat().st_mode & 0o7777)
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
        return copy
    except Exception:                          # noqa: BLE001 — a version is never worth a write
        return None


def path(dotted, default=None):
    """Same as conf(), but returns an absolute Path (~ expanded, relative to ROOT)."""
    value = conf(dotted, default)
    if value is None:
        return None
    p = Path(os.path.expanduser(str(value)))
    return p if p.is_absolute() else ROOT / p
