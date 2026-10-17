#!/usr/bin/env python
"""Probe: summary of the day's changes from changelog/.

changelog/YYYY-MM-DD.jsonl is filled by the PostToolUse hook (changelog/hook.py).
The argument is a YYYY-MM-DD date, today by default.
"""
import json, os, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

DIR = str(path("changelog.dir"))
day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
path = os.path.join(DIR, f"{day}.jsonl")


def load(p):
    recs = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return recs


def short(path_str, keep=2):
    """~/claude-home/status/probes/loe.py -> status/probes/loe.py"""
    p = path_str.replace("~/claude-home/", "")
    parts = p.split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else p


try:
    if not os.path.exists(path):
        print(json.dumps({"id": "changes", "ok": True, "severity": "quiet",
                          "value": {"day": day, "total": 0},
                          "text": f"Змін за {day} немає — журнал порожній",
                          "ttl": 300}, ensure_ascii=False))
        raise SystemExit

    recs = load(path)
    files = Counter(short(r["target"]) for r in recs if r.get("kind") != "bash")
    cmds = Counter(r["target"] for r in recs if r.get("kind") == "bash")
    sessions = len({r.get("session") for r in recs if r.get("session")})
    first = recs[0]["ts"][11:16] if recs else "—"
    last = recs[-1]["ts"][11:16] if recs else "—"
    edits = sum(files.values())

    lines = [f"Зміни за {day}: {len(recs)} подій — {edits} правок файлів, "
             f"{sum(cmds.values())} команд; {first}–{last}, сесій: {sessions}"]
    if files:
        lines.append("Файли: " + ", ".join(f"{n} ×{c}" for n, c in files.most_common(6))
                     + (f" та ще {len(files) - 6}" if len(files) > 6 else ""))
    if cmds:
        lines.append("Команди: " + ", ".join(f"{n} ×{c}" for n, c in cmds.most_common(6)))

    sev = "info" if recs else "quiet"
    print(json.dumps({"id": "changes", "ok": True, "severity": sev,
                      "value": {"day": day, "total": len(recs), "edits": edits,
                                "commands": sum(cmds.values()),
                                "files": files.most_common(10),
                                "cmds": cmds.most_common(10), "sessions": sessions},
                      "text": "\n".join(lines), "ttl": 300}, ensure_ascii=False))
except SystemExit:
    pass
except Exception as e:
    print(json.dumps({"id": "changes", "ok": False, "severity": "warn",
                      "text": f"Журнал змін не прочитався: {e}", "ttl": 300},
                     ensure_ascii=False))
