"""The task board — collectors for screen 9.

Named `tasks_screen` rather than `tasks` on purpose: `tasks/` is a package directory in
this repository and `tasks/store.py` is imported by several scripts, so a module called
`tasks` on the panel's path would shadow it in a way that only shows up at run time.

Pure over a `state()` dict. Writes are not here — the screen's route runs `store.py`, so
the log stays append-only and its validation stays in one place.
"""
from __future__ import annotations

from datetime import date, datetime


def minutes(t: dict) -> int:
    """Actual time spent, from the start/stop pairs — the same arithmetic `store.py` does,
    repeated here rather than imported so this module stays pure over plain dicts."""
    total = 0
    for r in t.get("runs") or []:
        try:
            a = datetime.fromisoformat(r["from"])
            b = datetime.fromisoformat(r["to"]) if r.get("to") else datetime.now().astimezone()
            total += max(0, int((b - a).total_seconds() // 60))
        except (KeyError, TypeError, ValueError):
            continue
    return total


def card(tid: str, t: dict, today: date | None = None) -> dict:
    """One task as the board shows it."""
    today = today or date.today()
    due = t.get("due") or ""
    overdue = bool(due and due < today.isoformat() and t.get("status") == "open")
    events = t.get("events") or []
    return {
        "id": tid,
        "title": t.get("title", ""),
        "project": t.get("project") or "",
        "due": due,
        "period": t.get("period") or None,
        "overdue": overdue,
        "today": bool(due and due == today.isoformat()),
        "estimate": t.get("estimate") or 0,
        "spent": minutes(t),
        "running": bool(t.get("running")),
        "block": bool(t.get("block")),
        "status": t.get("status", "open"),
        "plan": [e for e in events if e.get("kind", "plan") == "plan"],
        "fact": [e for e in events if e.get("kind") == "fact"],
    }


def columns(state: dict, today: date | None = None, closed_days: int = 3) -> dict:
    """The four columns.

    A task that is both overdue and carries a period lands in «Сьогодні» only: the date is
    the stronger claim, and a card in two columns is a card that gets done twice or not at
    all.
    """
    today = today or date.today()
    cutoff = today.toordinal() - closed_days
    out = {"today": [], "period": [], "backlog": [], "closed": []}
    for tid, t in state.items():
        c = card(tid, t, today)
        if t.get("status") != "open":
            when = (t.get("closed") or "")[:10]
            try:
                if when and date.fromisoformat(when).toordinal() < cutoff:
                    continue
            except ValueError:
                pass
            c["closed_at"] = when
            out["closed"].append(c)
        elif c["overdue"] or c["today"]:
            out["today"].append(c)
        elif c["period"] or c["due"]:
            # a hard future date is scheduled-for-later too — the board's own «завтра»
            # button makes one, and in «Беклог» it read as demoted and dateless (t1077)
            out["period"].append(c)
        else:
            out["backlog"].append(c)
    out["today"].sort(key=lambda c: (not c["overdue"], c["due"]))

    def starts(c):
        """What begins sooner comes first: a due date against a period's start. A period
        shorter than [kind, from, to] sorts last instead of crashing the board (t1077)."""
        if c["due"]:
            return c["due"]
        p = c["period"]
        return str(p[1]) if isinstance(p, list) and len(p) > 1 else "9999"
    out["period"].sort(key=starts)
    out["closed"].sort(key=lambda c: c.get("closed_at", ""), reverse=True)
    return out


def period_text(period) -> str:
    """«вихідні 31.10-01.11» from the log's `[kind, from, to]`."""
    if not isinstance(period, list) or len(period) < 3:
        return str(period or "")
    kind, start, end = period[0], str(period[1]), str(period[2])
    return f"{kind} {start[8:10]}.{start[5:7]}-{end[8:10]}.{end[5:7]}"
