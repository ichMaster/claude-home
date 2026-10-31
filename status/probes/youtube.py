#!/usr/bin/env python
"""Probe: new videos from the channels we follow.

Source is YouTube's per-channel RSS — plain HTTPS, no API key and no OAuth, so it
works headless too:
    https://www.youtube.com/feeds/videos.xml?channel_id=UC...

Channels come from config.json (`probes.youtube.channels`), each entry being
{"name": "...", "id": "UC..."} or {"name": "...", "handle": "@name"}. A handle is
resolved to a channel id once and cached in state, because the RSS endpoint only
accepts ids.

State (`status/state/youtube.json`) keeps the ids already reported, so "new" means
"not seen at the previous check" rather than "published recently".

With hundreds of subscriptions, polling every feed on every run would be both slow and
rude to YouTube, so each run takes a rotating window of `probes.youtube.per_run`
channels (the cursor lives in state) and fetches them in a small thread pool. Channels
listed in `probes.youtube.priority` are polled on every run regardless of the window.
"""
import json, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

STATE = path("paths.home") / "status" / "state" / "youtube.json"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
TTL = conf("probes.youtube.ttl", 1800)
MAX_AGE_DAYS = conf("probes.youtube.max_age_days", 3)
# every run appends what it found to state["pending"]; `--drain` prints the whole
# accumulated set and clears it, which is how the once-a-day YouTube digest works
# despite each run only polling a rotating window of channels
DRAIN = "--drain" in sys.argv
LAST = "--last" in sys.argv        # reprint the previous digest instead of draining
MAX_SHOWN = conf("probes.youtube.max_shown", 6)
PER_RUN = conf("probes.youtube.per_run", 80)
WORKERS = conf("probes.youtube.workers", 8)
PRIORITY = set(conf("probes.youtube.priority", []))
SKIP_SHORTS = conf("probes.youtube.skip_shorts", True)
DELAY = conf("probes.youtube.request_delay_sec", 0.4)
COOLDOWN_MIN = conf("probes.youtube.block_cooldown_min", 120)
UA = {"User-Agent": "Mozilla/5.0"}


def out(**kw):
    kw.setdefault("id", "youtube")
    kw.setdefault("ttl", TTL)
    print(json.dumps(kw, ensure_ascii=False))
    sys.exit(0)


def fetch(url, timeout=20):
    # YouTube soft-blocks the feeds endpoint when it is hit too fast: every channel
    # starts answering 404 while the channel pages still return 200
    if DELAY:
        time.sleep(DELAY)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def resolve_handle(handle):
    """A handle page carries the channel id in a meta tag; resolved once, then cached."""
    page = fetch(f"https://www.youtube.com/{handle.lstrip('@').join(['@', ''])}")
    m = re.search(r'"channelId":"(UC[\w-]{20,})"', page)
    return m.group(1) if m else None


def entries(xml):
    """Minimal Atom parsing: id, title, link, published — no external dependencies."""
    out_ = []
    for block in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        def tag(name, attr=None):
            if attr:
                m = re.search(rf'<{name}[^>]*{attr}="([^"]+)"', block)
            else:
                m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
            return m.group(1).strip() if m else ""
        out_.append({"vid": tag("yt:videoId"), "title": tag("title"),
                     "link": tag("link", "href"), "published": tag("published"),
                     "author": tag("name")})
    return out_


channels = conf("probes.youtube.channels", [])
if not channels:
    out(ok=False, severity="warn", ttl=3600,
        text="YouTube: канали не налаштовані. Додай їх у config.json → "
             "probes.youtube.channels (назва + id або handle)")

if LAST:
    saved = STATE.parent / "youtube-last-digest.json"
    if not saved.exists():
        out(ok=False, severity="warn", text="Попереднього дайджесту не збережено")
    data = json.loads(saved.read_text(encoding="utf-8"))
    items = data.get("items", [])
    lines = [f"YouTube, дайджест від {data['drained_at'][:16].replace('T', ' ')}: {len(items)} відео"]
    for e in items:
        lines.append(f"  • {e['channel']}: {e['title']}\n    {e['link']}")
    out(ok=True, severity="info", value={"new": len(items), "items": items},
        text="\n".join(lines))

state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
pending = state.get("pending", [])

# circuit breaker: while YouTube is blocking us, stop hammering it
blocked_until = state.get("blocked_until", "")
if blocked_until and datetime.now(timezone.utc).isoformat() < blocked_until and not DRAIN:
    out(ok=True, severity="quiet", ttl=600,
        value={"new": 0, "blocked_until": blocked_until},
        text=f"YouTube: опитування призупинено до {blocked_until[11:16]} UTC — "
             f"сервіс віддавав 404 на всі канали")
seen = set(state.get("seen", []))
resolved = state.get("resolved", {})
cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

fresh, broken = [], []

# rotate through the subscription list so one run touches a bounded slice of it
cursor = int(state.get("cursor", 0))
ordered = [c for c in channels if (c.get("name") or c.get("id")) in PRIORITY]
rest = [c for c in channels if c not in ordered]
if rest:
    window = rest[cursor:cursor + PER_RUN]
    if len(window) < PER_RUN:
        window += rest[: PER_RUN - len(window)]
    cursor = (cursor + PER_RUN) % len(rest)
    ordered += window


def poll(ch):
    name = ch.get("name") or ch.get("handle") or ch.get("id")
    cid = ch.get("id") or resolved.get(ch.get("handle", ""))
    try:
        if not cid and ch.get("handle"):
            cid = resolve_handle(ch["handle"])
            if cid:
                resolved[ch["handle"]] = cid
        if not cid:
            return name, [], "не знайшов id каналу"
        found = []
        for e in entries(fetch(FEED.format(cid))):
            if not e["vid"] or e["vid"] in seen:
                continue
            try:
                when = datetime.fromisoformat(e["published"])
            except ValueError:
                when = datetime.now(timezone.utc)
            # Shorts are the bulk of the feed and almost never worth an interruption
            if SKIP_SHORTS and "/shorts/" in e["link"]:
                seen.add(e["vid"])
                continue
            e["channel"], e["when"] = name, when
            found.append(e)
        return name, found, None
    except Exception as exc:
        return name, [], str(exc)


with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    for name, found, err in pool.map(poll, ordered):
        if err:
            broken.append(f"{name}: {err}")
            continue
        for e in found:
            if e["when"] < cutoff:
                seen.add(e["vid"])      # old video seen for the first time: remember, do not report
            else:
                fresh.append(e)

# all requests failing means a block, not 600 dead channels
if ordered and len(broken) >= max(3, int(0.8 * len(ordered))):
    until = (datetime.now(timezone.utc) + timedelta(minutes=COOLDOWN_MIN)).isoformat()
    state["blocked_until"] = until
    STATE.write_text(json.dumps({**state, "pending": pending}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    out(ok=False, severity="warn", ttl=600,
        value={"new": 0, "blocked_until": until, "errors": broken[:3]},
        text=f"YouTube: {len(broken)} з {len(ordered)} каналів віддали помилку — схоже на "
             f"тимчасове блокування. Пауза на {COOLDOWN_MIN} хв.")
state.pop("blocked_until", None)

fresh.sort(key=lambda e: e["when"], reverse=True)
seen.update(e["vid"] for e in fresh)

# accumulate for the daily digest, de-duplicated by video id
known = {p["link"] for p in pending}
pending += [{"channel": e["channel"], "title": e["title"], "link": e["link"],
             "published": e["published"]} for e in fresh if e["link"] not in known]
pending = pending[-200:]

# A longer archive than `pending`, which the digest empties every evening: Bruno searches
# the subscriptions by topic (the owner, 2026-10-30 — searching all of YouTube "буде багато
# трешу", so his own 600 channels are the filter). Append-only, trimmed by age on write.
archive = STATE.parent / "youtube-archive.jsonl"
if fresh:
    kept = []
    if archive.exists():
        keep_after = (datetime.now(timezone.utc)
                      - timedelta(days=conf("probes.youtube.archive_days", 45))).isoformat()
        for line in archive.read_text(encoding="utf-8").splitlines():
            if line.strip() and line.find('"published": "') > 0:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("published", "") >= keep_after:
                    kept.append(rec)
    have = {r.get("link") for r in kept}
    kept += [{"channel": e["channel"], "title": e["title"], "link": e["link"],
              "published": e["published"]} for e in fresh if e["link"] not in have]
    archive.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                               for r in kept[-20000:]), encoding="utf-8")
if DRAIN:
    drained, pending = pending, []
STATE.parent.mkdir(parents=True, exist_ok=True)
STATE.write_text(json.dumps({"seen": sorted(seen)[-4000:], "resolved": resolved,
                             "pending": pending,
                             "cursor": cursor, "checked_channels": len(ordered),
                             "checked": datetime.now().isoformat(timespec="seconds")},
                            ensure_ascii=False, indent=1), encoding="utf-8")

if DRAIN:
    # keep a copy so "send it again" never has to re-poll the channels
    if drained:
        (STATE.parent / "youtube-last-digest.json").write_text(
            json.dumps({"drained_at": datetime.now().isoformat(timespec="seconds"),
                        "items": drained}, ensure_ascii=False, indent=1), encoding="utf-8")
    if not drained:
        out(ok=True, severity="quiet", value={"new": 0, "items": []},
            text="YouTube: нових відео немає")
    lines = [f"YouTube: {len(drained)} нових відео з минулого дайджесту"]
    for e in drained:
        lines.append(f"  • {e['channel']}: {e['title']}\n    {e['link']}")
    out(ok=not broken, severity="info",
        value={"new": len(drained), "items": drained, "errors": broken},
        text="\n".join(lines))

if not fresh:
    text = "YouTube: нових відео немає"
    if broken:
        text += "\n  ! " + "; ".join(broken)
    out(ok=not broken, severity="quiet", value={"new": 0, "errors": broken}, text=text)

lines = [f"YouTube: {len(fresh)} нових відео"]
for e in fresh[:MAX_SHOWN]:
    lines.append(f"  • {e['channel']}: {e['title']}\n    {e['link']}")
if len(fresh) > MAX_SHOWN:
    lines.append(f"  … і ще {len(fresh) - MAX_SHOWN}")
if broken:
    lines.append("  ! " + "; ".join(broken))

out(ok=not broken, severity="info",
    value={"new": len(fresh),
           "items": [{"channel": e["channel"], "title": e["title"], "link": e["link"],
                      "published": e["published"]} for e in fresh[:20]],
           "errors": broken},
    text="\n".join(lines))
