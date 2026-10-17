#!/usr/bin/env python
"""Probe: task state — overdue, due today, coming up."""
import json, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

HOME = path("paths.home")
sys.path.insert(0, str(HOME / "tasks"))

try:
    from store import state  # type: ignore
    tasks = [(k, v) for k, v in state().items() if v["status"] == "open"]
    today = date.today()

    def due(v):
        return date.fromisoformat(v["due"]) if v.get("due") else None

    overdue = [(k, v) for k, v in tasks if due(v) and due(v) < today]
    now = [(k, v) for k, v in tasks if due(v) == today]
    soon = [(k, v) for k, v in tasks if due(v) and today < due(v) <= date.fromordinal(today.toordinal() + 7)]
    backlog = [(k, v) for k, v in tasks if not due(v)]

    if not tasks:
        print(json.dumps({"id": "tasks", "ok": True, "severity": "quiet",
                          "value": {"open": 0}, "text": "Задач немає", "ttl": 120},
                         ensure_ascii=False))
        raise SystemExit

    def line(k, v, mark):
        proj = f" [{v['project']}]" if v.get("project") else ""
        return f"  {mark} {v['title']}{proj}"

    periods = [(k, v) for k, v in tasks if v.get("period") and not due(v)]
    blocks = [(k, v) for k, v in tasks if v.get("block")]
    backlog = [(k, v) for k, v in backlog if not v.get("period")]

    def pline(k, v):
        kind, a, b = v["period"]
        a_, b_ = date.fromisoformat(a), date.fromisoformat(b)
        span = f"{a_:%d.%m}" if a_ == b_ else f"{a_:%d.%m}-{b_:%d.%m}"
        proj = f" [{v['project']}]" if v.get("project") else ""
        return f"  ~ {v['title']}{proj} ({kind} {span})"

    rows = ([line(k, v, "‼") for k, v in overdue]
            + [line(k, v, "⚠") for k, v in now]
            + [line(k, v, "·") for k, v in soon[:4]]
            + [pline(k, v) for k, v in periods[:3]])
    head = (f"Задачі: {len(tasks)} відкритих — прострочено {len(overdue)}, "
            f"на сьогодні {len(now)}, цього тижня {len(soon)}, "
            f"на період {len(periods)}, у беклозі {len(backlog)}; "
            f"у календар іде {len(blocks)}")
    print(json.dumps({"id": "tasks", "ok": True,
                      "severity": "warn" if overdue or now else "info",
                      "value": {"open": len(tasks), "overdue": len(overdue),
                                "today": len(now), "week": len(soon),
                                "backlog": len(backlog), "periods": len(periods),
                                "blocks": len(blocks)},
                      "text": "\n".join([head] + rows), "ttl": 120},
                     ensure_ascii=False))
except SystemExit:
    pass
except Exception as e:
    print(json.dumps({"id": "tasks", "ok": False, "severity": "warn",
                      "text": f"Задачі недоступні: {e}", "ttl": 300}, ensure_ascii=False))
