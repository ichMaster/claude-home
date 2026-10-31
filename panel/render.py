"""HTML for the panel — f-strings and `html.escape`, nothing else.

No template engine and no build step on purpose: the panel's job is to be the thing that
still works, including on a machine with no internet (docs/features/ADMIN-PANEL.md §
Interaction).

Everything interpolated goes through `e()`. A probe's text looks machine-made, but the mail
probe puts a sender's subject line in it and a subject is written by whoever sent the mail;
the change log holds command lines. Neither is trusted.
"""
from __future__ import annotations

from html import escape

SCREENS = [
    ("/", "Пульс"),
    ("/changes", "Зміни"),
    ("/zirka", "Зірка"),
    ("/bruno", "Бруно"),
    ("/prompt", "Промпт"),
    ("/scenarios", "Сценарії"),
    ("/memory", "Памʼять"),
    ("/sources", "Джерела"),
    ("/rules", "Правила"),
    ("/tasks", "Задачі"),
    ("/chat", "Чат"),
]


def e(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def age_text(age: int | None, ttl: int) -> str:
    """«2 хв тому», and the TTL beside it so staleness is checkable by eye."""
    if age is None:
        return "невідомо коли"
    if age < 90:
        when = f"{age} с тому"
    elif age < 5400:
        when = f"{age // 60} хв тому"
    else:
        when = f"{age // 3600} год тому"
    return f"{when} / TTL {ttl // 60} хв" if ttl else when


def page(title: str, body: str, active: str, refresh: int = 0) -> str:
    rail = "\n".join(
        f'<a class="{"on" if href == active else ""}" href="{e(href)}">{e(name)}</a>'
        for href, name in SCREENS)
    meta = f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else ""
    return f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}<title>{e(title)} · Ноос</title>
<link rel="stylesheet" href="/static/panel.css"></head>
<body><nav class="rail"><b>Ноос</b>
{rail}
</nav><main>{body}</main></body></html>
"""


def _probe_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">Пробники не відповіли.</p>'
    out = []
    for r in rows:
        stale = ' <span class="stale">застаріле</span>' if r["stale"] else ""
        broken = "" if r["ok"] else ' <span class="stale">помилка</span>'
        out.append(
            f'<tr class="{e(r["css"])}">'
            f'<td class="dot">{e(r["mark"])}</td>'
            f'<td class="id">{e(r["id"])}</td>'
            f'<td class="text">{e(r["text"])}{broken}</td>'
            f'<td class="age">{e(age_text(r["age"], r["ttl"]))}{stale}</td></tr>')
    return '<table class="probes">' + "".join(out) + "</table>"


def _timer_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">Таймерів не знайдено.</p>'
    out = ['<table class="timers"><tr><th>юніт<th>наступний<th>останній<th>як пройшов</tr>']
    for r in rows:
        verdict = "—"
        if r["failed"]:
            verdict = f'<span class="alert">{e(r["result"])}' + \
                      (f' ({e(r["exit"])})' if r["exit"] else "") + "</span>"
        elif r["result"]:
            verdict = "успішно"
        off = "" if r["enabled"] else ' <span class="stale">вимкнений</span>'
        out.append(f'<tr><td class="id">{e(r["unit"])}{off}'
                   f'<td>{e(r["next"])}<td>{e(r["last"])}<td>{verdict}</tr>')
    return "".join(out) + "</table>"


def _queue_list(q: dict) -> str:
    blocked = (f' <span class="warn">пауза до {e(q["youtube_blocked"][11:16])} UTC</span>'
               if q.get("youtube_blocked") else "")
    loud = ", ".join(q.get("watch_loud") or []) or "тиша"
    return (
        '<ul class="queues">'
        f'<li>ютюб: {q["youtube_pending"]} чекає на дайджест, '
        f'{q["youtube_seen"]} у памʼяті{blocked}</li>'
        f'<li>пошта: останній UID {e(q["mail_last_uid"])}'
        + (f', перевірено {e(q["mail_checked"][:16].replace("T", " "))}'
           if q.get("mail_checked") else "") + "</li>"
        f'<li>вартовий голосно про: {e(loud)}</li>'
        "</ul>")


def _changes_list(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">Сьогодні записів немає.</p>'
    out = []
    for r in rows:
        ts = str(r.get("ts") or "")[11:19]
        out.append(f'<tr><td class="age">{e(ts)}</td>'
                   f'<td class="id">{e(r.get("kind"))}</td>'
                   f'<td class="text">{e(r.get("target"))}</td>'
                   f'<td class="text dim">{e((r.get("detail") or "")[:90])}</td></tr>')
    return '<table class="changes">' + "".join(out) + "</table>"


def render_pulse(probes: list[dict], timers: list[dict], q: dict,
                 changes: list[dict], refresh: int = 30) -> str:
    """The status board. Nothing here is a form — phase 1 is read-only by design."""
    body = (
        "<h1>Пульс</h1>"
        "<section><h2>Пробники</h2>" + _probe_table(probes) + "</section>"
        "<section><h2>Таймери</h2>" + _timer_table(timers) + "</section>"
        "<section><h2>Черги</h2>" + _queue_list(q) + "</section>"
        "<section><h2>Останні зміни</h2>" + _changes_list(changes) + "</section>")
    return page("Пульс", body, "/", refresh)


def _commit_table(rows: list[dict], details: dict[str, dict]) -> str:
    if not rows:
        return '<p class="empty">Комітів немає.</p>'
    out = ['<table class="commits"><tr><th>коміт<th>дата<th>що<th>задача'
           '<th>ревʼю безпеки</tr>']
    for r in rows:
        d = details.get(r["sha"]) or {}
        task = (f'<span class="id">{e(r["task"])}</span>' if r["task"]
                else '<span class="warn">без задачі</span>')
        if d.get("task_title"):
            task += f'<br><span class="dim">{e(d["task_title"])}</span>'
        extra = []
        if d.get("spec"):
            extra.append(f'<span class="dim">спека</span>')
        elif r["task"]:
            extra.append('<span class="warn">спеки нема</span>')
        if d.get("tests"):
            extra.append(f'<span class="dim">тести: {e(", ".join(d["tests"]))}</span>')
        elif r["task"]:
            extra.append('<span class="warn">тестів нема</span>')
        # An absent reading and a clean reading must never look the same: a blank cell
        # would read as "nothing found" when it means "nobody wrote it down".
        review = ('<span class="dim">є</span>' if d.get("review")
                  else '<span class="warn">не записано</span>')
        local = ' <span class="stale">локальний</span>' if r["local"] else ""
        out.append(f'<tr><td class="id">{e(r["short"])}{local}'
                   f'<td class="age">{e(r["date"])}'
                   f'<td class="text">{e(r["subject"])}'
                   + (f'<br><span class="dim">{" · ".join(extra)}</span>' if extra else "")
                   + f'<td>{task}<td>{review}</tr>')
    return "".join(out) + "</table>"


def _nights_block(nights: list[dict]) -> str:
    if not nights:
        return '<p class="empty">Ревʼю ще не було.</p>'
    out = []
    for n in nights:
        counts = n.get("counts") or {}
        summary = ", ".join(f"{k}: {v}" for k, v in
                            sorted(counts.items(), key=lambda kv: kv[0])) or "не розібрано"
        out.append(f'<details><summary>{e(n["key"])} — {e(summary)}</summary>'
                   f'<pre>{e(n.get("scan", ""))}</pre>'
                   + (f'<pre>{e(n["fixes"])}</pre>' if n.get("fixes") else
                      '<p class="empty">Звіту про фікси немає.</p>')
                   + "</details>")
    return "".join(out)


def _lows_block(lows: list[dict]) -> str:
    if not lows:
        return '<p class="empty">Накопичених Low немає.</p>'
    out = ['<table class="lows"><tr><th>з якої ночі<th>ночей<th>знахідка</tr>']
    for low in sorted(lows, key=lambda x: x["since"]):
        out.append(f'<tr><td class="age">{e(low["since"])}<td class="age">{low["nights"]}'
                   f'<td class="text">{e(low["title"])}</tr>')
    return "".join(out) + "</table>"


def render_changes(rows: list[dict], details: dict[str, dict], nights: list[dict],
                   lows: list[dict], ahead: int | None, changes: list[dict],
                   query: str = "") -> str:
    """Screen 10 — what was built and how it was reviewed. Read-only, like all of phase 2."""
    # «Усе запушено» may only mean a verified zero; None means git had no answer.
    if ahead is None:
        push = '<p class="warn">origin недоступний — стан пушу невідомий.</p>'
    elif ahead:
        push = (f'<p><b class="warn">{int(ahead)}</b> комітів попереду origin — чекають '
                f'на ранковий пуш.</p>')
    else:
        push = '<p class="dim">Усе запушено.</p>'
    search = (f'<form method="get" class="search">'
              f'<input name="q" value="{e(query)}" placeholder="пошук у журналі змін">'
              f'<button type="submit">знайти</button></form>')
    body = (
        "<h1>Зміни й ревʼю</h1>"
        f"<section><h2>Пуш</h2>{push}</section>"
        "<section><h2>Коміти</h2>" + _commit_table(rows, details) + "</section>"
        "<section><h2>Нічні ревʼю</h2>" + _nights_block(nights) + "</section>"
        "<section><h2>Накопичені Low</h2>" + _lows_block(lows) + "</section>"
        "<section><h2>Журнал змін</h2>" + search + _changes_list(changes) + "</section>")
    return page("Зміни", body, "/changes")


def render_soon(title: str, href: str, phase: str) -> str:
    """A screen that has its place in the rail but not its code yet. Saying which phase
    builds it beats a dead link or a blank page."""
    body = (f"<h1>{e(title)}</h1>"
            f'<p class="empty">Цей екран ще не побудований — {e(phase)}.<br>'
            'Опис: <code>docs/features/ADMIN-PANEL.md</code>.</p>')
    return page(title, body, href)
