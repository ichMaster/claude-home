#!/usr/bin/env python
"""Remember which news have already been sent, so a digest never repeats itself.

  news_seen.py --mark <url> [<url> ...] [--title "…"]   record what was just sent
  news_seen.py --check <url>                            prints new | seen
  news_seen.py --filter                                 stdin: candidate blocks,
                                                        stdout: the same minus seen ones
  news_seen.py --list [days]                            what was sent recently

State is `status/state/news.json`: link plus a normalized title fingerprint, so the same
story from a second source is recognised as a repeat. Entries older than
`digest.news_memory_days` are forgotten.
"""
import json, re, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

STATE = path("paths.home") / "status" / "state" / "news.json"
MEMORY_DAYS = conf("digest.news_memory_days", 14)
OVERLAP = conf("digest.news_title_overlap", 0.6)
STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "for", "is", "as", "at", "by",
        "про", "під", "над", "для", "що", "як", "на", "в", "у", "із", "з", "та", "і"}


def words(title):
    t = re.sub(r"[^\w\s]", " ", (title or "").lower())
    return {w for w in t.split() if len(w) > 2 and w not in STOP}


def load():
    if not STATE.exists():
        return []
    try:
        items = json.loads(STATE.read_text(encoding="utf-8")).get("sent", [])
    except Exception:
        return []
    cutoff = (datetime.now() - timedelta(days=MEMORY_DAYS)).isoformat()
    return [i for i in items if i.get("ts", "") >= cutoff]


def save(items):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"sent": items[-500:]}, ensure_ascii=False, indent=1),
                     encoding="utf-8")


def seen_reason(items, url, title=""):
    """Why this candidate counts as already sent, or None.

    Returns the reason rather than a bare yes: the dedup is the piece most likely to be
    wrong, and until the panel could show *what* it dropped and *against what*, a story
    silently missing from a digest looked exactly like a story that never existed (t1072).
    """
    url = (url or "").split("?")[0].rstrip("/")
    if url:
        for i in items:
            if (i.get("url") or "").split("?")[0].rstrip("/") == url:
                return {"reason": "link", "matched": i.get("title") or "", "score": 1.0}
    w = words(title)
    if not w:
        return None
    for i in items:
        prev = set(i.get("words") or [])
        if not prev:
            continue
        common = w & prev
        # overlap against the shorter headline: "Путін заявив про зону безпеки на 660 км"
        # and "Путін оголосив зону безпеки шириною 660 кілометрів" are one story, even
        # though the second is longer. At least three shared words to avoid false hits.
        score = len(common) / min(len(w), len(prev))
        if len(common) >= 3 and score >= OVERLAP:
            return {"reason": "overlap", "matched": i.get("title") or "",
                    "score": round(score, 2), "common": sorted(common)}
    return None


def is_seen(items, url, title=""):
    return seen_reason(items, url, title) is not None


def record_drop(rec):
    """Best-effort log of one dropped candidate. Never allowed to break the filter: the
    digest's job is to go out, and this record is only so the panel can show the work."""
    try:
        f = STATE.parent / "news-dropped.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main():
    """The CLI. Guarded so the module can be imported by tests and by the
    panel without running a command (t1072)."""
    args = sys.argv[1:]
    items = load()

    if "--mark" in args:
        i = args.index("--mark")
        title = args[args.index("--title") + 1] if "--title" in args else ""
        urls = [a for a in args[i + 1:] if a.startswith("http")]
        now = datetime.now().isoformat(timespec="seconds")
        for u in urls:
            items.append({"url": u, "title": title, "words": sorted(words(title)), "ts": now})
        save(items)
        print(f"запам'ятав {len(urls)}")

    elif "--check" in args:
        url = args[args.index("--check") + 1]
        title = args[args.index("--title") + 1] if "--title" in args else ""
        print("seen" if is_seen(items, url, title) else "new")

    elif "--filter" in args:
        # candidate blocks look like "[N] Title (source)\n    https://…\n    lead…"
        text = sys.stdin.read()
        out, skipped = [], 0
        for block in re.split(r"\n(?=\[[A-Za-zА-Яа-я]+[#\]])", text):
            m_url = re.search(r"https?://\S+", block)
            m_title = re.match(r"\s*\[[^\]]+\]\s*(.+?)\s*(?:\(|\n)", block)
            title = m_title.group(1) if m_title else ""
            why = seen_reason(items, m_url.group(0), title) if m_url else None
            if why:
                skipped += 1
                record_drop({"ts": datetime.now().isoformat(timespec="seconds"),
                             "title": title, "url": m_url.group(0), **why})
                continue
            out.append(block)
        sys.stdout.write("\n".join(out))
        print(f"\n# відкинуто як уже надіслані: {skipped}", file=sys.stderr)

    elif "--list" in args:
        days = int(args[args.index("--list") + 1]) if len(args) > args.index("--list") + 1 and args[-1].isdigit() else 7
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        for i in [x for x in items if x.get("ts", "") >= cutoff][-40:]:
            print(f"{i['ts'][:10]}  {(i.get('title') or i['url'])[:80]}")

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
