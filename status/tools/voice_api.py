#!/usr/bin/env python
"""Real usage from the voice providers' own APIs, not from our local log.

The local `voice-usage.jsonl` only knows what *this* machine synthesized. The
ElevenLabs account is shared with other agents (lumi and friends), so the number that
matters — how much of the monthly quota is gone — can only come from the provider.

  ElevenLabs: GET /v1/user/subscription  -> character_count, character_limit, reset
  Deepgram:   GET /v1/projects/{id}/usage -> requests and seconds for a date range
              (needs a key with the `usage:read` scope; without it we fall back)

Results are cached in `status/state/usage-api.json` for `usage.api_cache_ttl` seconds,
so probe runs every 15 minutes do not hammer the providers.

  voice_api.py            print the merged JSON
  voice_api.py --fresh    ignore the cache
"""
import json, os, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

TIMEOUT = conf("usage.api_timeout", 8)
CACHE_TTL = conf("usage.api_cache_ttl", 600)
CACHE = path("usage.api_cache") or (Path(__file__).resolve().parents[1] / "state" / "usage-api.json")


def env(name):
    """Read a key from the environment, falling back to `.env.voice` (mode 600)."""
    if os.environ.get(name):
        return os.environ[name]
    f = path("voice.env") or Path.home() / "claude-home" / ".env.voice"
    if not f.exists():
        return None
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line or line.startswith("#"):
            continue
        k, v = line.split("=", 1)
        if k.strip() == name:
            return v.strip().strip('"').strip("'")
    return None


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def elevenlabs():
    key = env("ELEVENLABS_API_KEY")
    if not key:
        return {"error": "немає ключа"}
    try:
        d = get(conf("usage.elevenlabs.api_url", "https://api.elevenlabs.io/v1/user/subscription"),
                {"xi-api-key": key})
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)[:80]}

    used = int(d.get("character_count") or 0)
    limit = int(d.get("character_limit") or 0)
    reset = d.get("next_character_count_reset_unix")
    res = {"tier": d.get("tier"), "used": used, "limit": limit,
           "percent": round(used / limit * 100, 1) if limit else None,
           "status": d.get("status")}
    if reset:
        reset_dt = datetime.fromtimestamp(int(reset), timezone.utc)
        res["reset"] = reset_dt.date().isoformat()
        days_left = max(0.0, (reset_dt - datetime.now(timezone.utc)).total_seconds() / 86400)
        res["days_left"] = round(days_left, 1)
        # the billing period is a calendar month; what is gone of it is 30 - days_left
        elapsed = max(0.5, 30 - days_left)
        res["elapsed_days"] = round(elapsed, 1)
        res["per_day"] = int(used / elapsed)
        projected = used / elapsed * 30
        res["projected"] = int(projected)
        res["projected_percent"] = round(projected / limit * 100, 1) if limit else None
        # extrapolating from one or two days says more about the last day than the month
        res["projection_reliable"] = elapsed >= conf("usage.projection_min_days", 5)
    inv = (d.get("next_invoice") or {}).get("amount_due_cents")
    if inv:
        res["next_invoice_usd"] = round(inv / 100, 2)
    over = (d.get("current_overage") or {}).get("amount")
    if over and str(over) not in ("0", "0.0"):
        res["overage"] = str(over)
    return res


def deepgram():
    key = env("DEEPGRAM_API_KEY")
    if not key:
        return {"error": "немає ключа"}
    h = {"Authorization": f"Token {key}"}
    base = conf("usage.deepgram.api_url", "https://api.deepgram.com/v1/projects")
    project = conf("usage.deepgram.project_id", "")
    try:
        if not project:
            projects = (get(base, h).get("projects") or [])
            if not projects:
                return {"error": "немає проєктів"}
            project = projects[0]["project_id"]
        start = date.today().replace(day=1).isoformat()
        end = (date.today() + timedelta(days=1)).isoformat()
        d = get(f"{base}/{project}/usage?start={start}&end={end}", h)
    except urllib.error.HTTPError as e:
        # 403 is the normal case for a key without the usage:read scope
        return {"error": "ключу бракує scope usage:read" if e.code == 403 else f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)[:80]}

    res = d.get("results") or []
    requests_ = sum(int(r.get("requests") or 0) for r in res)
    hours = sum(float(r.get("total_hours") or 0) for r in res)
    return {"project": project, "month_requests": requests_,
            "month_hours": round(hours, 2), "month_minutes": round(hours * 60, 1)}


def read_cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else None
    except Exception:
        return None


def collect(fresh=False):
    cached = read_cache()
    if not fresh and cached and time.time() - cached.get("fetched_at", 0) < CACHE_TTL:
        cached["cached"] = True
        return cached

    data = {"fetched_at": time.time(), "elevenlabs": elevenlabs(), "deepgram": deepgram()}
    # a provider that failed this time keeps its last good answer, marked stale: a dropped
    # request should not look like "the quota is unknown" for the next cache window
    for name in ("elevenlabs", "deepgram"):
        if data[name].get("error") and cached and not (cached.get(name) or {}).get("error"):
            stale = dict(cached[name])
            stale["stale"] = True
            stale["last_error"] = data[name]["error"]
            data[name] = stale
    if any(not data[n].get("error") for n in ("elevenlabs", "deepgram")):
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    data["cached"] = False
    return data


if __name__ == "__main__":
    print(json.dumps(collect("--fresh" in sys.argv), ensure_ascii=False, indent=2))
