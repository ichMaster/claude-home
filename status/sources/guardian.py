#!/usr/bin/env python
"""Джерело: The Guardian Content API — статті з текстом, а не лише заголовки.

  guardian.py "<запит>" [розділ] [скільки]

Повертає JSON-масив кандидатів: заголовок, анотація, повний текст, посилання.
"""
import json, sys, urllib.parse, urllib.request, re, html
from pathlib import Path

cfg = Path.home() / "claude-home" / ".env.news"
env = dict(l.strip().split("=", 1) for l in cfg.read_text().splitlines() if "=" in l)
KEY = env["GUARDIAN_API_KEY"]

q = sys.argv[1]
section = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
n = int(sys.argv[3]) if len(sys.argv) > 3 else 12

params = {"q": q, "api-key": KEY, "order-by": "newest", "page-size": n,
          "show-fields": "trailText,bodyText,firstPublicationDate"}
if section:
    params["section"] = section
url = "https://content.guardianapis.com/search?" + urllib.parse.urlencode(params)

with urllib.request.urlopen(url, timeout=25) as r:
    d = json.load(r)

out = []
for a in d["response"]["results"]:
    f = a.get("fields") or {}
    body = re.sub(r"\s+", " ", html.unescape(f.get("bodyText", "")))
    out.append({"source": "The Guardian", "title": a["webTitle"],
                "section": a.get("sectionName", ""), "published": a.get("webPublicationDate", ""),
                "url": a["webUrl"],
                "lead": re.sub(r"<[^>]+>", "", html.unescape(f.get("trailText", ""))),
                "body": body[:6000]})
print(json.dumps(out, ensure_ascii=False))
