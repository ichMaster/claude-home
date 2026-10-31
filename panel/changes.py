"""What was built and how it was reviewed — the collectors for screen 10.

The process (CLAUDE.md § Development process) is real and invisible: a task, a spec, tests
written first, a commit naming the task id, a security reading of the staged diff, a
nightly self-review. The verdicts are spoken once into a chat and scroll away. This module
reconstructs the record from what is on disk — git, `tasks/`, `tests/`, and the two report
directories — and is read-only, like all of phase 2.

Parsing note: the review reports are Markdown this project generates itself, so reading
their headings is reading a format we control. Anything that does not match is handed back
raw rather than guessed at.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf                                               # noqa: E402

HOME = Path(__file__).resolve().parents[1]
SPECS = HOME / "tasks" / "specs"
TESTS = HOME / "tests"
COMMIT_REVIEW = HOME / "status" / "state" / "commit-review"

TASK_ID = re.compile(r"\((t\d{3,5})\)")
# `## High` / `## Medium (…)` / `## Low (reported, not fixed)` and the findings under them
SEVERITY_HEAD = re.compile(r"^##\s+(High|Medium|Low)\b", re.IGNORECASE | re.MULTILINE)
FINDING_HEAD = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
LOG_FORMAT = "%H%x1f%cI%x1f%s%x1f%an"


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True,
                         cwd=str(HOME), timeout=30)
    return out.stdout if out.returncode == 0 else ""


def ahead_hashes() -> set[str]:
    """Commits not yet on the public remote. Empty when there is no remote ref to compare
    against — an unknown answer must not be rendered as "everything is pushed"."""
    out = git("rev-list", "origin/main..HEAD")
    return {h.strip() for h in out.splitlines() if h.strip()}


def commit_rows(log: str, ahead: set[str] | None = None) -> list[dict]:
    """Parse `git log --format=LOG_FORMAT` into rows.

    A commit with no `(t####)` is flagged rather than quietly accepted: the process says
    there should not be one, and the screen is where that shows.
    """
    ahead = ahead or set()
    rows = []
    for line in (log or "").splitlines():
        parts = line.split("\x1f")
        if len(parts) < 3:
            continue
        sha, when, subject = parts[0], parts[1], parts[2]
        m = TASK_ID.search(subject)
        rows.append({
            "sha": sha,
            "short": sha[:7],
            "date": when[:16].replace("T", " "),
            "subject": subject,
            "task": m.group(1) if m else "",
            "no_task": not m,
            "local": sha in ahead,
            "author": parts[3] if len(parts) > 3 else "",
        })
    return rows


def commit_detail(row: dict, tasks: dict | None = None) -> dict:
    """The spec, the tests and the security reading behind one commit.

    Every absence is named. A spec that does not exist is `None` and rendered as missing —
    the one thing this screen must never do is make an unchecked commit look checked.
    """
    task_id = row.get("task") or ""
    spec = SPECS / f"{task_id}.md" if task_id else None
    tests = []
    if task_id and TESTS.is_dir():
        for f in sorted(TESTS.glob("test_*.py")):
            try:
                if task_id in f.read_text(encoding="utf-8"):
                    tests.append(f.name)
            except OSError:
                continue
    review = COMMIT_REVIEW / f"{row['sha']}.md"
    title = ""
    if tasks and task_id in tasks:
        title = tasks[task_id].get("title", "")
    return {
        "task_title": title,
        "spec": str(spec.relative_to(HOME)) if spec and spec.is_file() else None,
        "tests": tests,
        "review": review.read_text(encoding="utf-8") if review.is_file() else None,
    }


def files_of(sha: str) -> list[str]:
    return [f for f in git("show", "--name-only", "--format=", sha).splitlines() if f.strip()]


# --- the nightly reviews ----------------------------------------------------------------

def findings(report: str) -> dict[str, list[str]]:
    """Finding titles grouped by severity, from a scan report's own headings.

    Returns `{}` for anything that does not look like one of our reports, so the caller can
    show it raw instead of pretending to have understood it.
    """
    out: dict[str, list[str]] = {}
    marks = list(SEVERITY_HEAD.finditer(report or ""))
    if not marks:
        return {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(report)
        severity = m.group(1).lower()
        titles = [t.group(1).strip() for t in FINDING_HEAD.finditer(report[m.end():end])]
        out.setdefault(severity, []).extend(titles)
    return out


def review_nights(report_dir: Path | None = None) -> list[dict]:
    """One row per review: its date, the scan and fix reports, and counts by severity."""
    d = report_dir or (HOME / str(conf("codereview.report_dir", "status/state/code-review")))
    if not d.is_dir():
        return []
    nights: dict[str, dict] = {}
    for f in sorted(d.glob("*.md")):
        name = f.stem
        kind = "fixes" if name.endswith("-fixes") else "scan" if name.endswith("-scan") else ""
        if not kind:
            continue
        key = name.rsplit("-", 1)[0]
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        night = nights.setdefault(key, {"key": key, "date": key[:10], "scan": "",
                                        "fixes": "", "counts": {}, "parsed": False})
        night[kind] = text
        if kind == "scan":
            found = findings(text)
            night["counts"] = {k: len(v) for k, v in found.items()}
            night["parsed"] = bool(found)
    return sorted(nights.values(), key=lambda n: n["key"], reverse=True)


def open_lows(nights: list[dict]) -> list[dict]:
    """Low findings across every night, deduplicated, oldest first.

    Lows are reported and never fixed, so they accumulate where nobody sees the pile grow.
    Keeping the night each was first raised is the whole point: an item that has been open
    for a fortnight says something an item raised last night does not.
    """
    seen: dict[str, dict] = {}
    for night in sorted(nights, key=lambda n: n["key"]):
        for title in findings(night.get("scan", "")).get("low", []):
            key = title.split("(")[0].strip().lower()
            seen.setdefault(key, {"title": title, "since": night["date"],
                                  "nights": 0})["nights"] += 1
    return list(seen.values())
