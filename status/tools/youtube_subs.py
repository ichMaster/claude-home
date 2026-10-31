#!/usr/bin/env python
"""Daily check for newly-followed YouTube channels (t1040).

The owner's subscription list is private — only the Data API `subscriptions.list` with OAuth
can read it (no key-only or RSS path). So this stays **dormant until** a one-time login exists
(`status/tools/youtube_oauth.py` writes a refresh token to `.env.youtube`). With creds it runs
daily: fetch the current subscriptions, diff against the channels already in
`config.local.json` (`probes.youtube.channels`), report additions in the morning and append
them to the polling list so the archive starts covering them.

Nothing is ever deleted from the polling list: a channel you unsubscribed from may still have
videos worth the archive. Removals are reported, not applied.

    youtube_subs.py              # the daily run (dormant without creds)
    youtube_subs.py --dry-run    # fetch + diff, report to stdout, change nothing
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HOME))
from noosconf import atomic_write_text, conf, path                      # noqa: E402

TOKEN_URL = "https://oauth2.googleapis.com/token"
SUBS_URL = "https://www.googleapis.com/youtube/v3/subscriptions"


def creds() -> dict:
    """Read OAuth creds from `.env.youtube` (git-ignored, mode 600). Missing → empty, and the
    job stays dormant rather than erroring."""
    f = Path(str(conf("probes.youtube.oauth_env", "~/claude-home/.env.youtube"))).expanduser()
    out: dict[str, str] = {}
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def access_token(c: dict) -> str:
    body = urllib.parse.urlencode({
        "client_id": c["YT_CLIENT_ID"], "client_secret": c["YT_CLIENT_SECRET"],
        "refresh_token": c["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def fetch_subscriptions(c: dict) -> list[dict]:
    """Every subscription as {id, name}, following pagination. Raises on API/network error so
    the caller can report and change nothing."""
    token = access_token(c)
    out, page = [], ""
    while True:
        q = {"part": "snippet", "mine": "true", "maxResults": "50", "order": "alphabetical"}
        if page:
            q["pageToken"] = page
        req = urllib.request.Request(f"{SUBS_URL}?{urllib.parse.urlencode(q)}",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        for it in data.get("items", []):
            sn = it.get("snippet", {})
            cid = sn.get("resourceId", {}).get("channelId")
            if cid:
                out.append({"id": cid, "name": sn.get("title", cid)})
        page = data.get("nextPageToken", "")
        if not page:
            break
    return out


def diff_subs(stored_ids: set[str], fetched: list[dict]) -> tuple[list[dict], list[str]]:
    """Pure: which fetched channels are new, which stored ids are no longer subscribed.
    `stored_ids` are the channel ids already polled; `fetched` the current subscriptions."""
    fetched_ids = {f["id"] for f in fetched}
    new = [f for f in fetched if f["id"] not in stored_ids]
    removed = [i for i in stored_ids if i not in fetched_ids]
    return new, removed


def stored_channels() -> list[dict]:
    return conf("probes.youtube.channels") or []


def append_channels(new: list[dict]) -> None:
    """Add new channels to config.local.json's polling list. That file is personal and
    git-ignored; we only ever append."""
    f = Path(str(path("paths.home"))) / "config.local.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    chans = data.setdefault("probes", {}).setdefault("youtube", {}).setdefault("channels", [])
    have = {c.get("id") for c in chans}
    for n in new:
        if n["id"] not in have:
            chans.append({"name": n["name"], "id": n["id"]})
    # atomic: a torn write here would destroy the only copy of the personal config (t1043)
    atomic_write_text(f, json.dumps(data, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="щоденна перевірка нових підписок YouTube")
    ap.add_argument("--dry-run", action="store_true", help="порахувати, нічого не змінювати")
    args = ap.parse_args()

    c = creds()
    need = {"YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"}
    if not need.issubset(c):
        print("немає OAuth-доступу (.env.youtube) — джоба в сплячці; "
              "запусти status/tools/youtube_oauth.py один раз")
        return 0

    try:
        fetched = fetch_subscriptions(c)
    except Exception as e:                                               # noqa: BLE001
        print(f"не вдалось прочитати підписки: {e} — нічого не змінюю")
        return 0
    if not fetched:
        print("підписок не отримано — нічого не змінюю")
        return 0

    stored = stored_channels()
    new, removed = diff_subs({s.get("id") for s in stored if s.get("id")}, fetched)
    print(f"підписок у YouTube: {len(fetched)}, у списку опитування: {len(stored)}, "
          f"нових: {len(new)}, відписаних: {len(removed)}")
    for n in new:
        print(f"  + {n['name']}")

    if args.dry_run or not new:
        return 0

    append_channels(new)
    names = ", ".join(n["name"] for n in new[:15]) + (" …" if len(new) > 15 else "")
    spoken = (f"Нові підписки на ютюбі, {len(new)}: {names}. Додав у опитування, "
              f"відео з них зʼявляться в пошуку за кілька годин.")
    import subprocess
    subprocess.run([str(HOME / "notify.sh"), "--bot", "youtube", "--voice-profile", "news",
                    "--voice-text", spoken,
                    f"🔔 Нові підписки YouTube ({len(new)}):\n" +
                    "\n".join(f"• {n['name']}" for n in new)],
                   check=False, cwd=str(HOME), timeout=120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
