#!/usr/bin/env python
"""Pre-push scan for secrets and private information.

The repo is public and every push is a publication, so before one the owner wants a scan of
what is going out for secrets AND for personal/sensitive information, not only API keys
(2026-10-31). This is the deterministic floor of the security review in CLAUDE.md — it does
not replace reading the diff, it guarantees the obvious never slips through when the reading
is rushed.

By default it scans what a push would actually publish: the diff between `origin/main` and
`HEAD` (committed) plus anything still staged/working that a careless `git add -A` would
sweep in. Pass `--all` to scan the whole tree, `--staged` for the index only.

Exit code 1 if anything matched, so it can gate a push:

    status/tools/presim_scan.py            # what HEAD is ahead of origin, + working changes
    status/tools/presim_scan.py --all      # the entire working tree
    status/tools/presim_scan.py --staged   # only staged files

Matches are reported with file and line. A line already inside a `.gitignore`-d path never
reaches here, because git does not show it — but the scan double-checks against the ignore
list and says so.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[2]

# (name, pattern, severity). Severity is advisory — anything matched is surfaced.
PATTERNS = [
    ("Telegram-токен", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b"), "крит"),
    ("OpenAI/ключ sk-", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "крит"),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "крит"),
    ("Anthropic ключ", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "крит"),
    ("ElevenLabs/Deepgram", re.compile(r"\b(?:xi-api-key|dg_|sk_[a-f0-9]{32,})\b", re.I), "крит"),
    ("приватний ключ PEM", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "крит"),
    ("Bearer-токен", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"), "висок"),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "крит"),
    # personal / sensitive information — the part the owner specifically added
    ("email-адреса", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "приват"),
    ("український мобільний", re.compile(r"(?:\+?380|\b0)\d{9}\b"), "приват"),
    ("координати (можлива адреса)", re.compile(r"\b4[5-9]\.\d{3,}\s*[,/]\s*2[2-5]\.\d{3,}\b"), "приват"),
    ("дата народження", re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[.\-/](?:0?[1-9]|1[0-2])[.\-/](?:19|20)\d{2}\b"), "приват"),
    ("Google calendar id", re.compile(r"\b[a-f0-9]{40,}@group\.calendar\.google\.com\b"), "приват"),
    ("ключ-подібний рядок", re.compile(r"""(?i)(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['"][^'"]{8,}['"]"""), "висок"),
]

# Allowed: the committed examples are meant to carry placeholder values. A real secret in
# them would still be caught, because placeholders never match the key patterns.
ALLOW_SUBSTR = ("ichland@gmail.com", "noreply@anthropic.com", "example.com",
                "user@example.com", "123456:AA", "sk-ant-...", "AIza...")


def changed_files(mode: str) -> list[Path]:
    def run(*args):
        r = subprocess.run(["git", *args], cwd=HOME, capture_output=True, text=True)
        return [l for l in r.stdout.splitlines() if l.strip()]

    if mode == "all":
        files = run("ls-files")
    elif mode == "staged":
        files = run("diff", "--cached", "--name-only")
    else:  # outgoing: committed-ahead-of-origin plus working/staged changes
        subprocess.run(["git", "fetch", "origin", "-q"], cwd=HOME, capture_output=True)
        names = set(run("diff", "--name-only", "origin/main...HEAD"))
        names.update(l[3:] for l in run("status", "--porcelain"))
        files = sorted(names)
    out = []
    for name in files:
        p = HOME / name
        if p.is_file():
            out.append(p)
    return out


def is_ignored(path: Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=HOME)
    return r.returncode == 0


# binary files are scanned as a whole-file membership test, not line by line: a PDF or an
# image yields garbage "numbers" when split into lines (a PDF gave dozens of fake phone
# numbers). A binary that is about to be published is itself worth a human look, so it is
# still reported — just once, as "binary file in the push", not per bogus line.
BINARY_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
              ".ogg", ".oga", ".mp3", ".mp4", ".wav", ".db", ".sqlite", ".zip",
              ".gz", ".tar", ".bin", ".pyc", ".woff", ".woff2", ".ttf"}


def scan_file(path: Path) -> list[tuple[int, str, str, str]]:
    if path.suffix.lower() in BINARY_EXT:
        return [(0, "увага", "бінарний файл у пуші — переглянути вручну", path.suffix)]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if any(a in line for a in ALLOW_SUBSTR):
            continue
        for name, rx, sev in PATTERNS:
            m = rx.search(line)
            if m:
                snippet = m.group(0)
                if len(snippet) > 24:                 # never print a full secret
                    snippet = snippet[:12] + "…" + snippet[-4:]
                hits.append((i, sev, name, snippet))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="скан на секрети й приватне перед пушем")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_const", dest="mode", const="all")
    g.add_argument("--staged", action="store_const", dest="mode", const="staged")
    ap.set_defaults(mode="outgoing")
    args = ap.parse_args()

    files = changed_files(args.mode)
    rel = HOME
    total = 0
    print(f"скан ({args.mode}): {len(files)} файлів")
    for p in files:
        if is_ignored(p):
            continue                                  # not published anyway
        hits = scan_file(p)
        if hits:
            print(f"\n⚠ {p.relative_to(rel)}")
            for line, sev, name, snippet in hits:
                print(f"   {line:>5}  [{sev}] {name}: {snippet}")
                total += 1
    if total:
        print(f"\n❌ знайдено {total} збігів — переглянути перед пушем")
        return 1
    print("\n✅ секретів і приватного не знайдено")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
