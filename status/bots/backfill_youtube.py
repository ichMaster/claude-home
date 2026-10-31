#!/usr/bin/env python
"""One-off: fill the subscription archive from every channel's RSS, so Bruno's video search
has history on day one.

The archive (`status/state/youtube-archive.jsonl`) is normally appended to by the `youtube`
probe, which only ever sees *new* videos — so it grows at about 160 a day and a search for
anything narrow comes back empty for the first weeks. Each channel feed carries its last
~15 videos regardless of age, which for 600 subscriptions is roughly nine thousand entries
and months of depth for the quieter channels.

It deliberately does **not** touch `youtube.json`: `seen`, `pending` and the cursor stay as
they are, so the daily digest still reports exactly what it would have reported. The archive
is a separate file with a separate purpose.

YouTube soft-blocks the feeds endpoint when hit too fast — every channel starts answering
404 while the channel pages still work — so this walks at the probe's own pace
(`probes.youtube.request_delay_sec`, `probes.youtube.workers`) and stops early if most
requests start failing, rather than pushing through and getting the probe blocked too.

    backfill_youtube.py              every channel
    backfill_youtube.py --limit 50   the first 50, to try it out
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf                                               # noqa: E402

HOME = Path(__file__).resolve().parents[2]
ARCHIVE = HOME / "status" / "state" / "youtube-archive.jsonl"
STATE = HOME / "status" / "state" / "youtube.json"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {"a": "http://www.w3.org/2005/Atom"}
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url: str, delay: float) -> bytes:
    if delay:
        time.sleep(delay)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def entries(blob: bytes, name: str) -> list[dict]:
    root = ElementTree.fromstring(blob)
    out = []
    for e in root.findall("a:entry", NS):
        link_el = e.find("a:link", NS)
        link = link_el.get("href", "") if link_el is not None else ""
        title = (e.findtext("a:title", default="", namespaces=NS) or "").strip()
        published = (e.findtext("a:published", default="", namespaces=NS) or "").strip()
        if not link or not title or "/shorts/" in link:
            continue
        out.append({"channel": name, "title": title, "link": link, "published": published})
    return out


def load_archive() -> tuple[list[dict], set[str]]:
    rows, have = [], set()
    if ARCHIVE.exists():
        for line in ARCHIVE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("link") and r["link"] not in have:
                have.add(r["link"])
                rows.append(r)
    return rows, have


def main() -> int:
    ap = argparse.ArgumentParser(description="наповнити архів підписок з RSS")
    ap.add_argument("--limit", type=int, help="скільки каналів узяти")
    args = ap.parse_args()

    channels = conf("probes.youtube.channels") or []
    resolved = {}
    if STATE.exists():
        resolved = json.loads(STATE.read_text(encoding="utf-8")).get("resolved", {})
    targets = []
    for ch in channels:
        cid = ch.get("id") or resolved.get(ch.get("handle", ""))
        if cid:
            targets.append((ch.get("name") or cid, cid))
    if args.limit:
        targets = targets[: args.limit]
    delay = float(conf("probes.youtube.request_delay_sec", 0.4))
    workers = int(conf("probes.youtube.workers", 8))
    print(f"каналів: {len(targets)}, затримка {delay}s, потоків {workers}")

    rows, have = load_archive()
    print(f"в архіві вже: {len(rows)}")

    def one(t):
        name, cid = t
        try:
            return name, entries(fetch(FEED.format(cid), delay), name), None
        except Exception as e:                                           # noqa: BLE001
            return name, [], str(e)

    added, failed, done = 0, 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, found, err in pool.map(one, targets):
            done += 1
            if err:
                failed += 1
                # a wall of failures means the endpoint is blocking us, not that 600
                # channels died: stop and keep what we have
                if done >= 20 and failed >= 0.8 * done:
                    print(f"\n{failed} з {done} запитів впали — схоже на блокування, спиняюсь")
                    break
                continue
            for e in found:
                if e["link"] not in have:
                    have.add(e["link"])
                    rows.append(e)
                    added += 1
            if done % 50 == 0:
                print(f"  {done}/{len(targets)} каналів, +{added} відео")

    rows.sort(key=lambda r: r.get("published", ""))
    ARCHIVE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[-20000:]),
                       encoding="utf-8")
    days = sorted(r.get("published", "")[:10] for r in rows if r.get("published"))
    print(f"\nдодано {added}, в архіві {len(rows)}, "
          f"період {days[0] if days else '?'} … {days[-1] if days else '?'}, "
          f"каналів з помилкою {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
