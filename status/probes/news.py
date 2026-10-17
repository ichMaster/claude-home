#!/usr/bin/env python
"""Пробник новин за темою: news.py <тема>

Тема — файл status/topics/<тема>.json:
  {"назва": "...", "опис": "...", "запит": "...", "джерела": ["domain", ...],
   "ліміт": 5}

Шукає лише в межах указаних джерел (Google News RSS, без ключа) і віддає
тільки те, чого ще не надсилав — решта відсікається за посиланням.
"""
import json, sys, re, html, hashlib, urllib.request, urllib.parse
from pathlib import Path

HOME = Path.home() / "claude-home" / "status"
# заголовки-рубрики, які Google підсовує замість новин
JUNK = re.compile(r"(Latest News|Breaking (International )?News|Live updates|"
                  r"News & (Views|Updates)|Top stories|Home ?page|RSS|"
                  r"Останні новини|Головні новини сьогодні|News and Articles|"
                  r"articles,? and features|Rankings$|Hierarchy|Archives?$)", re.I)
tid = sys.argv[1]
topic = json.loads((HOME / "topics" / f"{tid}.json").read_text(encoding="utf-8"))
seen_file = HOME / "state" / f"news-{tid}.json"
seen = set(json.loads(seen_file.read_text()) if seen_file.exists() else [])

q = topic["запит"]
sites = topic.get("джерела") or []
if sites:
    q += " (" + " OR ".join(f"site:{s}" for s in sites) + ")"
lang = topic.get("мова", "uk")
loc = {"uk": ("uk", "UA", "UA:uk"), "en": ("en-US", "US", "US:en")}.get(lang, ("uk", "UA", "UA:uk"))
url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
       f"&hl={loc[0]}&gl={loc[1]}&ceid={loc[2]}")

try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        xml = r.read().decode("utf-8", "replace")
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    fresh, norms = [], []

    def similar(a):
        """Чи є вже майже такий самий заголовок — за перетином слів."""
        wa = {w for w in re.sub(r"[^\w ]", " ", a.lower()).split() if len(w) > 3}
        return any(len(wa & wb) >= max(3, len(wa) // 2) for wb in norms if wb)
    for it in items:
        link = re.search(r"<link>(.*?)</link>", it, re.S)
        title = re.search(r"<title>(.*?)</title>", it, re.S)
        src = re.search(r'<source[^>]*>(.*?)</source>', it, re.S)
        if not link or not title:
            continue
        link = html.unescape(link.group(1).strip())
        key = hashlib.sha1(link.encode()).hexdigest()[:12]
        if key in seen:
            continue

        name = html.unescape(src.group(1)) if src else ""
        clean = html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip()
        if name and clean.endswith(" - " + name):      # Google дублює джерело в заголовку
            clean = clean[: -len(name) - 3].strip()
        if not name or clean.lower() in (name.lower(), ""):   # домашні сторінки сайтів
            continue
        if JUNK.search(clean):                                # рубрики й головні сторінки
            continue
        if similar(clean):                                    # той самий сюжет з іншого сайту
            continue
        norms.append({w for w in re.sub(r"[^\w ]", " ", clean.lower()).split() if len(w) > 3})
        fresh.append({"title": clean,
                      "link": link, "source": name,
                      "key": key})
        if len(fresh) >= topic.get("ліміт", 5):
            break
    for f in fresh:
        seen.add(f["key"])
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text(json.dumps(sorted(seen)[-800:], ensure_ascii=False))

    if fresh:
        text = f"{topic['назва']}: {len(fresh)} нових\n" + "\n".join(
            f"• {f['title']} — {f['source']}" for f in fresh)
    else:
        text = f"{topic['назва']}: нічого нового"
    print(json.dumps({"id": f"news:{tid}", "ok": True,
                      "severity": "info" if fresh else "quiet",
                      "value": {"items": fresh, "query": q},
                      "text": text, "ttl": 3600}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"id": f"news:{tid}", "ok": False, "severity": "warn",
                      "text": f"Новини «{tid}» недоступні: {e}", "ttl": 300},
                     ensure_ascii=False))
