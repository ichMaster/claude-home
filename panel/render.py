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
    # A search that matched nothing is not an empty day — the default empty state would
    # read as "no such change was ever made".
    log_block = ('<p class="empty">Нічого не знайдено.</p>' if query and not changes
                 else _changes_list(changes))
    body = (
        "<h1>Зміни й ревʼю</h1>"
        f"<section><h2>Пуш</h2>{push}</section>"
        "<section><h2>Коміти</h2>" + _commit_table(rows, details) + "</section>"
        "<section><h2>Нічні ревʼю</h2>" + _nights_block(nights) + "</section>"
        "<section><h2>Накопичені Low</h2>" + _lows_block(lows) + "</section>"
        "<section><h2>Журнал змін</h2>" + search + log_block + "</section>")
    return page("Зміни", body, "/changes")


def _blocks_table(blocks: list[dict]) -> str:
    if not blocks:
        return '<p class="empty">Читання на цей день немає.</p>'
    out = ['<table class="blocks"><tr><th>блок<th>знаків<th>текст</tr>']
    for b in blocks:
        if b["missing"]:
            size = '<span class="warn">немає</span>'
            text = '<span class="dim">блок відсутній</span>'
        else:
            mark = "warn" if b["over"] else "dim"
            size = f'<span class="{mark}">{b["chars"]} / {b["budget"]}</span>'
            text = e(b["text"])
        out.append(f'<tr><td class="id">{e(b["name"])}<td class="age">{size}'
                   f'<td class="text">{text}</tr>')
    return "".join(out) + "</table>"


def _runs_block(runs: list[dict]) -> str:
    if not runs:
        return '<p class="empty">Прогонів за цей день у лозі немає.</p>'
    out = []
    for n, run in enumerate(runs, 1):
        names = ", ".join(s["name"] for s in run["stages"]) or "порожньо"
        out.append(f'<details><summary>прогін {n} — {e(names)}</summary>')
        for s in run["stages"]:
            out.append(f'<h3 class="stage">{e(s["name"])}</h3><pre>{e(s["text"])}</pre>')
        out.append("</details>")
    return "".join(out)


def _refs_block(refs: list[dict], parked: list[dict], token: str) -> str:
    out = []
    if parked:
        out.append('<h3 class="stage">Чекають на внесення (з чату Зірки)</h3>'
                   '<table class="parked">')
        for p in parked:
            out.append(
                f'<tr><td class="age">{e(p["day"])}<td class="age">{p["chars"]} зн.'
                f'<td class="text dim">{e(p["head"][:160])}…'
                f'<td><form method="post" action="/zirka">'
                f'<input type="hidden" name="token" value="{e(token)}">'
                f'<input type="hidden" name="action" value="ingest">'
                f'<input type="hidden" name="file" value="{e(p["name"])}">'
                f'<button type="submit">внести</button></form></tr>')
        out.append("</table>")
    if refs:
        out.append('<h3 class="stage">У сховищі</h3><table class="refs">')
        for r in refs:
            out.append(f'<tr><td class="age">{e(r.get("day"))}'
                       f'<td class="id">{e(r.get("author") or "без автора")}'
                       f'<td class="age">{len(r.get("text") or "")} зн.'
                       f'<td class="text dim">{e((r.get("text") or "")[:120])}…</tr>')
        out.append("</table>")
    elif not parked:
        out.append('<p class="empty">Еталонів ще немає.</p>')
    return "".join(out)


def _paste_form(token: str, day: str) -> str:
    """The write that earns the screen: a long reading survives a textarea where it does
    not survive Telegram."""
    return (
        '<form method="post" action="/zirka" class="paste">'
        f'<input type="hidden" name="token" value="{e(token)}">'
        '<input type="hidden" name="action" value="reference">'
        '<textarea name="text" rows="10" placeholder="вставити прогноз астролога"></textarea>'
        '<div class="row">'
        f'<label>день <input type="date" name="day" value="{e(day)}"></label>'
        '<label>автор <input name="author" placeholder="необовʼязково"></label>'
        '<label><input type="checkbox" name="learn" value="1" checked> одразу витягти правила</label>'
        '<button type="submit">зберегти</button>'
        "</div></form>")


def _actions(token: str, day: str) -> str:
    buttons = [("recalc", "перерахувати день"), ("ask", "спитати про день зараз"),
               ("calibrate", "калібрувати цей день")]
    out = ['<form method="post" action="/zirka" class="actions">',
           f'<input type="hidden" name="token" value="{e(token)}">',
           f'<input type="hidden" name="day" value="{e(day)}">']
    for value, label in buttons:
        out.append(f'<button type="submit" name="action" value="{value}">{e(label)}</button>')
    return "".join(out) + "</form>"


def render_zirka(day: str, blocks: list[dict], runs: list[dict], facts: list[str],
                 own_rules: str, ref_rules: str, feedback: list[dict], refs: list[dict],
                 parked: list[dict], token: str, message: str = "") -> str:
    """Screen 4 — the forecast pipeline, and the one form that solves a problem today."""
    note = f'<p class="note">{e(message)}</p>' if message else ""
    picker = (f'<form method="get" class="search"><label>день '
              f'<input type="date" name="day" value="{e(day)}"></label>'
              f'<button type="submit">показати</button></form>')
    fb = "".join(f'<tr><td class="age">{e(str(r.get("ts"))[:16].replace("T", " "))}'
                 f'<td class="text">{e(r.get("text"))}</tr>' for r in feedback)
    body = (
        f"<h1>Зірка — {e(day)}</h1>{note}{picker}"
        f"<section><h2>Дії</h2>{_actions(token, day)}</section>"
        f"<section><h2>Читання проти лімітів</h2>{_blocks_table(blocks)}</section>"
        f"<section><h2>Конвеєр</h2>{_runs_block(runs)}</section>"
        "<section><h2>Пораховані факти</h2><pre>"
        + e("\n".join(facts)) + "</pre></section>"
        "<section><h2>Правила з його днів</h2><pre>" + e(own_rules or "ще немає")
        + "</pre></section>"
        "<section><h2>Правила з прогнозів астролога</h2><pre>" + e(ref_rules or "ще немає")
        + "</pre></section>"
        "<section><h2>Відгуки про дні</h2>"
        + (f'<table class="feedback">{fb}</table>' if fb
           else '<p class="empty">Відгуків немає.</p>') + "</section>"
        f"<section><h2>Еталони</h2>{_refs_block(refs, parked, token)}"
        f"{_paste_form(token, day)}</section>")
    return page("Зірка", body, "/zirka")


def _dropped_table(rows: list[dict]) -> str:
    """The section the Bruno screen exists for: what the dedup threw away, and against
    what. A story silently absent from a digest is indistinguishable from one that never
    existed — until here."""
    if not rows:
        return ('<p class="empty">Нічого не відкидалось — або дайджест ще не ходив '
                'відтоді, як це почали записувати.</p>')
    out = ['<table class="dropped"><tr><th>коли<th>причина<th>кандидат<th>збіглось із</tr>']
    for r in rows:
        why = r.get("reason", "")
        label = {"link": "той самий лінк",
                 "overlap": f'перетин заголовків {r.get("score", "")}'}.get(why, why)
        out.append(f'<tr><td class="age">{e(str(r.get("ts"))[5:16].replace("T", " "))}'
                   f'<td class="warn">{e(label)}'
                   f'<td class="text">{e(r.get("title"))}'
                   f'<td class="text dim">{e(r.get("matched"))}</tr>')
    return "".join(out) + "</table>"


def _sent_block(news: list[dict], videos: tuple[str, list[dict]]) -> str:
    out = []
    if news:
        out.append('<h3 class="stage">Новини</h3><table class="sent">')
        for n in news:
            out.append(f'<tr><td class="age">{e(str(n.get("ts"))[:10])}'
                       f'<td class="text">{e(n.get("title"))}'
                       f'<td class="dim">{e(str(n.get("url"))[:60])}</tr>')
        out.append("</table>")
    when, items = videos
    if items:
        out.append(f'<h3 class="stage">Відео — добірка від {e(when[:16].replace("T", " "))}'
                   "</h3><table class=\"sent\">")
        for v in items:
            out.append(f'<tr><td class="id">{e(v.get("channel"))}'
                       f'<td class="text">{e(v.get("title"))}'
                       f'<td class="dim">{e(str(v.get("link"))[:50])}</tr>')
        out.append("</table>")
    return "".join(out) or '<p class="empty">Нічого ще не надсилалось.</p>'


def _archive_block(stats: dict, found: list[dict], query: str) -> str:
    head = (f'<p>{stats["count"]} відео з {stats["channels"]} каналів'
            + (f', з {e(stats["first"])} по {e(stats["last"])}' if stats["first"] else "")
            + ".</p>")
    form = (f'<form method="get" class="search">'
            f'<input name="q" value="{e(query)}" placeholder="слово в заголовку">'
            f'<button type="submit">знайти</button></form>')
    if query and not found:
        body = '<p class="empty">Нічого з таким словом в архіві немає.</p>'
    elif found:
        rows = "".join(f'<tr><td class="age">{e(str(r.get("published"))[:10])}'
                       f'<td class="id">{e(r.get("channel"))}'
                       f'<td class="text">{e(r.get("title"))}'
                       f'<td class="dim">{e(str(r.get("link"))[:50])}</tr>' for r in found)
        body = f'<table class="sent">{rows}</table>'
    else:
        body = ""
    return head + form + body


def _chat_block(chat: dict) -> str:
    turns = "".join(
        f'<tr><td class="id">{"він" if t.get("role") == "user" else "Бруно"}'
        f'<td class="text">{e(t.get("text"))}</tr>' for t in chat.get("history", []))
    drops = "".join(
        f'<tr><td class="age">{e(str(d.get("ts"))[5:16].replace("T", " "))}'
        f'<td class="warn">{e(d.get("why"))}'
        f'<td class="dim">{e(", ".join((d.get("shape") or {}).get("keys", [])) or "—")}</tr>'
        for d in chat.get("dropped", []))
    cap = (f'<p>Відповідей за останню годину: {chat.get("answers_this_hour", 0)} '
           f'із {chat.get("cap", 0)}.'
           + (f' Остання область пошуку: {e(chat["last_scope"])}.'
              if chat.get("last_scope") else "") + "</p>")
    return (cap
            + (f'<table class="chat">{turns}</table>' if turns
               else '<p class="empty">Розмови ще не було.</p>')
            + (f'<h3 class="stage">Відкинуті повідомлення</h3>'
               f'<table class="dropped">{drops}</table>' if drops else ""))


def _topics_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">Тем немає.</p>'
    out = ['<table class="topics"><tr><th>тема<th>запит<th>джерела</tr>']
    for t in rows:
        if t.get("broken"):
            out.append(f'<tr><td class="id">{e(t["id"])}'
                       f'<td class="alert" colspan="2">{e(t["broken"])}</tr>')
            continue
        out.append(f'<tr><td class="id">{e(t["name"] or t["id"])}'
                   f'<br><span class="dim">{e(t.get("about"))}</span>'
                   f'<td class="text dim">{e(t.get("query"))}'
                   f'<td class="dim">{e(", ".join(t.get("sources") or []))}</tr>')
    return "".join(out) + "</table>"


def render_bruno(news: list[dict], videos: tuple[str, list[dict]], dropped: list[dict],
                 stats: dict, found: list[dict], query: str, chat: dict,
                 topics: list[dict], prompts: list[dict]) -> str:
    """Screen 5 — what the content channel chose, out of what, and why. Read-only."""
    prompt_blocks = "".join(
        f'<details><summary>{e(p["name"])}</summary><pre>{e(p["text"])}</pre></details>'
        for p in prompts)
    body = (
        "<h1>Бруно</h1>"
        f"<section><h2>Що відкинуто як повтор</h2>{_dropped_table(dropped)}</section>"
        f"<section><h2>Що надіслано</h2>{_sent_block(news, videos)}</section>"
        f"<section><h2>Архів підписок</h2>{_archive_block(stats, found, query)}</section>"
        f"<section><h2>Його чат</h2>{_chat_block(chat)}</section>"
        f"<section><h2>Теми</h2>{_topics_table(topics)}</section>"
        f'<section><h2>Промпти</h2><p class="dim">Тільки читання — редагування з дифом '
        f'і банером перезапуску приходить у фазі 5.</p>{prompt_blocks}</section>')
    return page("Бруно", body, "/bruno")


def _task_card(c: dict, token: str) -> str:
    bits = []
    if c.get("project"):
        bits.append(f'[{e(c["project"])}]')
    if c.get("estimate"):
        bits.append(f'~{c["estimate"]} хв')
    if c.get("spent"):
        bits.append(("▶ " if c.get("running") else "⏱ ") + f'{c["spent"]} хв')
    if c.get("block"):
        bits.append("📌")
    if c.get("period"):
        bits.append(e(_period(c["period"])))
    if c.get("due"):
        mark = "warn" if c.get("overdue") else "dim"
        bits.append(f'<span class="{mark}">{e(c["due"])}</span>')
    if c.get("closed_at"):
        bits.append(f'закрито {e(c["closed_at"][:10])}')
    events = "".join(
        f'<div class="ev dim">{"🗓" if ev.get("kind", "plan") == "plan" else "✔"} '
        f'{e(str(ev.get("start"))[:16].replace("T", " "))}</div>'
        for ev in (c.get("plan") or []) + (c.get("fact") or []))

    def button(action: str, label: str, **extra) -> str:
        hidden = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">'
                         for k, v in extra.items())
        return (f'<form method="post" action="/tasks" class="inline">'
                f'<input type="hidden" name="token" value="{e(token)}">'
                f'<input type="hidden" name="id" value="{e(c["id"])}">{hidden}'
                f'<button type="submit" name="action" value="{e(action)}">{e(label)}</button>'
                "</form>")

    controls = ""
    if c.get("status") == "open":
        controls = (button("done", "закрити")
                    + button("stop" if c.get("running") else "start",
                             "зупинив" if c.get("running") else "почав")
                    + button("defer", "сьогодні", when="сьогодні")
                    + button("defer", "завтра", when="завтра")
                    + button("defer", "вихідні", when="на вихідних")
                    + button("block", "📌", on="off" if c.get("block") else "on"))
    return (f'<div class="card{" over" if c.get("overdue") else ""}">'
            f'<div class="t"><span class="id">{e(c["id"])}</span> {e(c["title"])}</div>'
            f'<div class="meta dim">{" · ".join(bits)}</div>{events}'
            f'<div class="controls">{controls}</div></div>')


def _period(period) -> str:
    if not isinstance(period, list) or len(period) < 3:
        return str(period or "")
    return f"{period[0]} {str(period[1])[8:10]}.{str(period[1])[5:7]}" \
           f"-{str(period[2])[8:10]}.{str(period[2])[5:7]}"


def render_tasks(cols: dict, token: str, message: str = "") -> str:
    """Screen 9 — four columns over the same append-only log the session reads.

    No drag and drop: the design asks for it, but it needs a client framework the same
    design forbids, and three buttons do the job on a page that must work with no
    internet. The deviation is a decision, written down in tasks/specs/t1074.md.
    """
    note = f'<p class="note">{e(message)}</p>' if message else ""
    add = ('<form method="post" action="/tasks" class="search">'
           f'<input type="hidden" name="token" value="{e(token)}">'
           '<input type="hidden" name="action" value="add">'
           '<input name="text" placeholder="нова задача — дату можна писати словами">'
           '<button type="submit">додати</button></form>')
    titles = {"today": "Сьогодні", "period": "Період", "backlog": "Беклог",
              "closed": "Закриті"}
    sections = ""
    for key in ("today", "period", "backlog", "closed"):
        cards = "".join(_task_card(c, token) for c in cols.get(key, []))
        sections += (f'<section><h2>{titles[key]} ({len(cols.get(key, []))})</h2>'
                     + (cards or '<p class="empty">Порожньо.</p>') + "</section>")
    return page("Задачі", f"<h1>Задачі</h1>{note}{add}{sections}", "/tasks")


def render_soon(title: str, href: str, phase: str) -> str:
    """A screen that has its place in the rail but not its code yet. Saying which phase
    builds it beats a dead link or a blank page."""
    body = (f"<h1>{e(title)}</h1>"
            f'<p class="empty">Цей екран ще не побудований — {e(phase)}.<br>'
            'Опис: <code>docs/features/ADMIN-PANEL.md</code>.</p>')
    return page(title, body, href)
