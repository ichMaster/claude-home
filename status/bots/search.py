#!/usr/bin/env python
"""Search for Bruno: news by topic, and videos inside the owner's own subscriptions.

He asked Bruno to be searchable rather than only a broadcaster (2026-10-30): say a topic,
get the five best items from the news and the five best videos, or only one of the two when
he says so.

Two very different sources, for one reason:

* **News — Bing News RSS search.** Plain HTTPS, no key, both Ukrainian and English. Bing
  rather than Google News for two concrete reasons: its items carry a real snippet from the
  body, and its links unwrap to the publisher's own URL, while Google News hides the target
  behind a JS-only token page (measured 2026-10-30) — which also makes fetching the article
  itself impossible. Its matching is better too: Google News answered «лідар» with «лідер».
* **Videos — the local archive of his subscriptions only.** Searching all of YouTube needs
  an API key and, in his words, «буде багато трешу»; his own 600 channels already are the
  quality filter. The archive is filled by the `youtube` probe on every run
  (`status/state/youtube-archive.jsonl`, trimmed to `probes.youtube.archive_days`).

**No relevance matching happens here** (the owner, 2026-10-31). News relevance is Bing's;
video candidates are the subscription archive by recency only. Which of them actually answer
the query is decided by the LLM (Bruno) that reads the titles — a regex score once dropped a
video whose title did not share the query's words.

    search.py news "лідар"            JSON: the news hits
    search.py youtube "lidar robot"   JSON: recent subscription videos (LLM picks from them)
    search.py both "квантові обчислення"
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf                                               # noqa: E402

HOME = Path(__file__).resolve().parents[2]
ARCHIVE = HOME / "status" / "state" / "youtube-archive.jsonl"
NEWS_RSS = "https://www.bing.com/news/search?q={}&format=RSS&mkt={}"
ARTICLE_CHARS = 1800            # enough for a model to find the substance, not the whole page
UA = {"User-Agent": "Mozilla/5.0"}


def norm(text: str) -> str:
    """Normalise a title for de-duplicating news hits only — never for relevance matching,
    which is the LLM's job (the owner, 2026-10-31)."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return re.sub(r"[^a-zа-яіїєґ0-9 ]+", " ", text)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def unwrap(link: str) -> str:
    """Bing wraps every link in `apiclick.aspx?...&url=<real>`. Unwrapping it gives the
    publisher's own address — which is what makes both a readable link and a fetchable
    article possible."""
    if "bing.com/news/apiclick" not in link:
        return link
    q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    return (q.get("url") or [link])[0]


def strip_html(blob: bytes) -> str:
    """Paragraph text out of a page, without a parser dependency: scripts and styles cut
    out, then `<p>` contents joined. Crude, and good enough to hand a model."""
    try:
        html = blob.decode("utf-8", "replace")
    except Exception:                                                    # noqa: BLE001
        return ""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    text = " ".join(re.sub(r"(?s)<[^>]+>", " ", p) for p in paras)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&laquo;", "«").replace("&raquo;", "»"))
    return re.sub(r"\s+", " ", text).strip()


def article(url: str) -> str:
    """The body of one article, for the two or three sentences of substance he asked for
    (2026-10-30: «на кожну новину був текст десь до 2-3 речення з середини новини»). A
    paywall or a block yields an empty string, and the snippet is used instead — never a
    guess at what the article says."""
    try:
        text = strip_html(fetch(url, timeout=12))
    except Exception:                                                    # noqa: BLE001
        return ""
    return text[:ARTICLE_CHARS]


def news(query: str, limit: int = 12, bodies: int = 8) -> list[dict]:
    """Bing News in both languages he reads, de-duplicated by title, with the article body
    fetched for the first `bodies` hits so the answer can quote substance."""
    out: list[dict] = []
    for mkt in ("uk-UA", "en-US"):
        url = NEWS_RSS.format(urllib.parse.quote(query), mkt)
        try:
            root = ElementTree.fromstring(fetch(url))
        except Exception as e:                                           # noqa: BLE001
            print(f"# пошук новин ({mkt}) не вдався: {e}", file=sys.stderr)
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = unwrap((item.findtext("link") or "").strip())
            if not title or not link:
                continue
            out.append({"title": title, "link": link,
                        "source": urllib.parse.urlparse(link).netloc.replace("www.", ""),
                        "snippet": re.sub(r"\s+", " ",
                                          (item.findtext("description") or "")).strip(),
                        "published": (item.findtext("pubDate") or "").strip(),
                        "lang": mkt[:2]})
    seen, uniq = set(), []
    for item in out:
        key = norm(item["title"])[:70]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    uniq = uniq[:limit]

    # fetch the bodies in parallel: a dozen sequential page loads would take half a minute
    head = uniq[:bodies]
    with ThreadPoolExecutor(max_workers=int(conf("telegram.inbox.fetch_workers", 4))) as pool:
        for item, text in zip(head, pool.map(lambda i: article(i["link"]), head)):
            item["text"] = text
    return uniq


def videos(query: str, limit: int = 0) -> list[dict]:
    """The subscription archive as a candidate pool — NO relevance matching here.

    The owner was firm (2026-10-31): matching is the LLM's job, not a regex script. A word-
    overlap score dropped a video whose title did not literally share the query's words. So
    this returns candidates by recency only (recency is a window, not a judgement of meaning),
    and Bruno — the answering LLM — reads the titles and decides what is relevant. `query` is
    kept in the signature for callers but deliberately not used to filter.
    """
    if not ARCHIVE.exists():
        return []
    rows = []
    for line in ARCHIVE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows.sort(key=lambda r: r.get("published", ""), reverse=True)
    pool = limit or int(conf("telegram.inbox.search_video_pool", 500))
    return rows[:pool]


def archive_span() -> str:
    """What the archive actually covers, so an empty result can be explained honestly
    rather than read as "there is nothing on this topic"."""
    if not ARCHIVE.exists():
        return "архів порожній"
    days = []
    count = 0
    for line in ARCHIVE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        try:
            d = json.loads(line).get("published", "")[:10]
        except json.JSONDecodeError:
            continue
        if d:
            days.append(d)
    if not days:
        return f"{count} відео, дати невідомі"
    return f"{count} відео, з {min(days)} по {max(days)}"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    what, query = sys.argv[1], " ".join(sys.argv[2:])
    result: dict = {"query": query}
    if what in ("news", "both"):
        result["news"] = news(query)
    if what in ("youtube", "both"):
        result["videos"] = videos(query)
        result["archive"] = archive_span()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
