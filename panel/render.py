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


def render_soon(title: str, href: str, phase: str) -> str:
    """A screen that has its place in the rail but not its code yet. Saying which phase
    builds it beats a dead link or a blank page."""
    body = (f"<h1>{e(title)}</h1>"
            f'<p class="empty">Цей екран ще не побудований — {e(phase)}.<br>'
            'Опис: <code>docs/features/ADMIN-PANEL.md</code>.</p>')
    return page(title, body, href)
