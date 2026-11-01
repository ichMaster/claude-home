#!/usr/bin/env python3
"""Previous contents of the files whose loss would hurt — list, compare, restore.

    tools/versions.py list [<file>]            what is kept, newest first
    tools/versions.py diff <file> [<stamp>]    that version against what is on disk now
    tools/versions.py restore <file> <stamp>   put it back (the current one is kept too)

A pile of dated copies nobody can navigate is not a backup; this is the part that makes
it one. `restore` goes through the same atomic write every other writer uses, so the file
it replaces becomes a version of its own — an undo can be undone (the owner asked for the
copies; this is the half that makes them usable, 2026-11-01).

Proper backup — off this machine, thinned by age, encrypted — is phase 10 of the panel
and deliberately not here. These copies live on the same disk and protect against a wrong
write, not against losing the disk.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import ROOT, _versions_root, atomic_write_text, conf, precious  # noqa: E402


def folder_for(target: Path) -> Path:
    try:
        rel = target.resolve().relative_to(ROOT)
    except ValueError:
        rel = Path(target.name)
    return _versions_root() / rel.parent / rel.name


def versions(target: Path) -> list[dict]:
    """Every kept copy of one file, newest first."""
    folder = folder_for(target)
    if not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.glob("*.bin"), reverse=True):
        stamp, _, rest = f.stem.partition(".")
        try:
            when = datetime.strptime(stamp, "%Y%m%dT%H%M%S%f")
        except ValueError:
            continue
        out.append({"stamp": stamp, "when": when.strftime("%Y-%m-%d %H:%M:%S"),
                    "digest": rest, "size": f.stat().st_size, "file": f})
    return out


def all_tracked() -> list[Path]:
    """Files that have at least one kept version."""
    root = _versions_root()
    if not root.is_dir():
        return []
    out = []
    for folder in sorted(root.rglob("*")):
        if folder.is_dir() and any(folder.glob("*.bin")):
            out.append(ROOT / folder.relative_to(root))
    return out


def pick(target: Path, stamp: str | None) -> dict | None:
    got = versions(target)
    if not got:
        return None
    if not stamp:
        return got[0]
    exact = [v for v in got if v["stamp"] == stamp or v["stamp"].startswith(stamp)]
    return exact[0] if exact else None


def diff_text(target: Path, version: dict) -> str:
    old = version["file"].read_text(encoding="utf-8", errors="replace").splitlines()
    new = (target.read_text(encoding="utf-8", errors="replace").splitlines()
           if target.is_file() else [])
    return "\n".join(difflib.unified_diff(
        old, new, fromfile=f"{target.name} @ {version['when']}",
        tofile=f"{target.name} зараз", lineterm="")) or "(однакові)"


def restore(target: Path, version: dict) -> str:
    """Put a version back. The file being replaced is itself versioned first, by the same
    write path, so this is reversible."""
    blob = version["file"].read_text(encoding="utf-8", errors="replace")
    atomic_write_text(target, blob)
    return (f"відновлено {target} з версії {version['when']} "
            f"({version['size']} байт); поточна теж збережена як версія")


def snapshot() -> list[str]:
    """Take a copy of the precious files nothing rewrites.

    An append-only log — the task log, a fact file that is never edited — has no write to
    hang a version on, and the owner's instruction was a periodic copy rather than
    versioning for those (2026-11-01). Run daily; the hash check means an unchanged file
    costs nothing.
    """
    from noosconf import keep_version                                   # noqa: E402

    done = []
    for rel in conf("versions.files", []) or []:
        p = Path(str(rel)).expanduser()
        if not p.is_absolute():
            p = ROOT / p
        targets = sorted(p.rglob("*")) if p.is_dir() else [p]
        for f in targets:
            if f.is_file() and keep_version(f):
                done.append(str(f.relative_to(ROOT) if str(f).startswith(str(ROOT)) else f))
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="версії файлів, які шкода втратити")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="зняти копію дописуваних файлів (щодня)")
    p_list = sub.add_parser("list", help="що збережено")
    p_list.add_argument("file", nargs="?")
    p_diff = sub.add_parser("diff", help="версія проти поточного файлу")
    p_diff.add_argument("file")
    p_diff.add_argument("stamp", nargs="?")
    p_res = sub.add_parser("restore", help="повернути версію")
    p_res.add_argument("file")
    p_res.add_argument("stamp")
    args = ap.parse_args()

    if args.cmd == "snapshot":
        done = snapshot()
        print(f"скопійовано {len(done)}: " + ", ".join(done[:8])
              + (" …" if len(done) > 8 else "") if done else "усе без змін")
        return 0

    if args.cmd == "list" and not args.file:
        tracked = all_tracked()
        if not tracked:
            print("версій ще немає")
            return 0
        for f in tracked:
            got = versions(f)
            rel = f.relative_to(ROOT) if str(f).startswith(str(ROOT)) else f
            print(f"{len(got):>3}  {rel}  (остання {got[0]['when']})")
        return 0

    target = Path(args.file).expanduser()
    if not target.is_absolute():
        target = ROOT / target

    if args.cmd == "list":
        got = versions(target)
        if not got:
            print(f"версій для {target} немає"
                  + ("" if precious(target) else " — і цей файл не в списку versions.files"))
            return 0
        for v in got:
            print(f"{v['stamp']}  {v['when']}  {v['size']:>8} байт  {v['digest']}")
        return 0

    v = pick(target, getattr(args, "stamp", None))
    if not v:
        print(f"такої версії немає: {args.stamp}", file=sys.stderr)
        return 1
    if args.cmd == "diff":
        print(diff_text(target, v))
        return 0
    print(restore(target, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
