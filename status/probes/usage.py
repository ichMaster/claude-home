#!/usr/bin/env python
"""Probe: how much was used today — tokens, synthesis and recognition.

Tokens come from the Claude Code transcripts under `~/.claude/projects`: every
assistant record carries a `usage` block (input, output, cache write, cache read) and
the model that produced it. Voice numbers come from `status/state/voice-usage.jsonl`,
appended by the voice scripts.

**ElevenLabs is a flat subscription**, so the number that matters is the monthly credit
quota, not a price per message. That quota is shared with other agents on the same
account (lumi and friends), so what is already spent is read from **the provider's own
API** (`status/tools/voice_api.py`), not from our local log — the local numbers only
know what this machine synthesized, and are reported alongside as "our share".
Tokens and recognition are plain counters — nothing is billed per token on a
subscription.

  usage.py [YYYY-MM-DD]     default: today
"""
import json, sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from noosconf import conf, path
import voice_api

DAY = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1][:2] == "20" else date.today().isoformat()
EL = conf("usage.elevenlabs", {})
EL_QUOTA = EL.get("credits_per_month", 0)
EL_PER_CHAR = EL.get("credits_per_char", 1.0)
EL_WARN = EL.get("warn_at_percent", 80)
TTL = conf("usage.ttl", 300)


def out(**kw):
    kw.setdefault("id", "usage")
    kw.setdefault("ttl", TTL)
    print(json.dumps(kw, ensure_ascii=False))
    sys.exit(0)


def money(x):
    return f"${x:.2f}" if x >= 0.995 else f"${x:.3f}"


def short(n):
    return f"{n/1_000_000:.2f}M" if n >= 1_000_000 else (f"{n//1000}k" if n >= 1000 else str(n))


try:
    tokens = defaultdict(lambda: defaultdict(int))     # model -> kind -> count
    sessions = set()
    for f in path("paths.transcripts").glob("**/*.jsonl"):
        if datetime.fromtimestamp(f.stat().st_mtime).date().isoformat() < DAY:
            continue
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if (rec.get("timestamp") or "")[:10] != DAY:
                    continue
                msg = rec.get("message") or {}
                u = msg.get("usage") or rec.get("usage") or {}
                if not u:
                    continue
                model = msg.get("model") or "невідома"
                if model.startswith("<"):        # <synthetic>: service records, not a model
                    continue
                tokens[model]["in"] += u.get("input_tokens", 0) or 0
                tokens[model]["out"] += u.get("output_tokens", 0) or 0
                tokens[model]["cache_w"] += u.get("cache_creation_input_tokens", 0) or 0
                tokens[model]["cache_r"] += u.get("cache_read_input_tokens", 0) or 0
                sessions.add(f.stem)

    total = defaultdict(int)
    for t in tokens.values():
        for k, v in t.items():
            total[k] += v

    # voice: one line per synthesis or recognition
    chars, seconds, tts_calls, stt_calls = 0, 0.0, 0, 0
    month_chars = 0
    month = DAY[:7]
    vlog = path("usage.voice_log")
    if vlog and vlog.exists():
        for line in vlog.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = r.get("ts") or ""
            if ts[:7] == month and r.get("kind") == "tts":
                month_chars += int(r.get("chars", 0))
            if ts[:10] != DAY:
                continue
            if r.get("kind") == "tts":
                chars += int(r.get("chars", 0)); tts_calls += 1
            elif r.get("kind") == "stt":
                seconds += float(r.get("seconds", 0)); stt_calls += 1

    all_tokens = sum(total.values())
    ours = month_chars * EL_PER_CHAR          # what this machine put through, for comparison

    # the account is shared, so the authoritative numbers come from the provider
    api = voice_api.collect("--fresh" in sys.argv)
    el = api.get("elevenlabs") or {}
    dg = api.get("deepgram") or {}
    el_ok = not el.get("error")
    quota = el.get("limit") or EL_QUOTA
    credits = el["used"] if el_ok else ours
    pct = credits / quota * 100 if quota else 0
    proj_pct = el.get("projected_percent") or 0
    proj_ok = bool(el.get("projection_reliable"))

    if not all_tokens and not chars and not seconds:
        out(ok=True, severity="quiet", value={"day": DAY},
            text=f"Використання за {DAY}: даних немає")

    lines = [f"Використання за {DAY}: {short(all_tokens)} токенів",
             f"  ввід {short(total['in'])}, вивід {short(total['out'])}, "
             f"кеш запис {short(total['cache_w'])}, кеш читання {short(total['cache_r'])}"]
    for model, t in sorted(tokens.items(), key=lambda kv: -sum(kv[1].values())):
        lines.append(f"    {model}: вивід {short(t['out'])}, ввід {short(t['in'])}")
    if chars or seconds:
        lines.append(f"  голос: синтез {short(chars)} символів ({tts_calls} разів), "
                     f"розпізнавання {seconds/60:.1f} хв ({stt_calls})")
    if el_ok and quota:
        stale = " (дані з кешу, API не відповів)" if el.get("stale") else ""
        lines.append(f"  ElevenLabs по акаунту: {short(credits)} з {short(quota)} кредитів "
                     f"({pct:.0f}%), план {el.get('tier') or EL.get('plan')}, "
                     f"обнулення {el.get('reset') or '?'} "
                     f"(через {el.get('days_left', '?')} дн.){stale}")
        if el.get("per_day"):
            tail = (f", за цим темпом — {proj_pct:.0f}% до обнулення" if proj_ok
                    else f" (минуло лише {el.get('elapsed_days')} дн., прогноз ненадійний)")
            lines.append(f"    темп {short(el['per_day'])} кредитів на день{tail}")
        if ours:
            share = ours / credits * 100 if credits else 0
            lines.append(f"    з них наші: {short(int(ours))} ({share:.0f}%) — решта з інших агентів")
        if el.get("next_invoice_usd"):
            lines.append(f"    наступний рахунок: ${el['next_invoice_usd']:.2f}")
        if el.get("overage"):
            lines.append(f"    перевищення: {el['overage']}")
    elif el.get("error"):
        lines.append(f"  ElevenLabs API недоступний ({el['error']}), "
                     f"локально за місяць: {short(int(ours))} кредитів")
    if dg.get("month_minutes") is not None and not dg.get("error"):
        lines.append(f"  Deepgram по акаунту: {dg['month_minutes']:.0f} хв за місяць "
                     f"({dg.get('month_requests', 0)} запитів)")
    lines.append(f"  сесій: {len(sessions)}")

    # warn on what is certain (the quota is really going) or on a projection worth trusting
    hot = pct >= EL_WARN or (proj_ok and proj_pct >= EL_WARN)
    out(ok=True, severity="warn" if hot else "info",
        value={"day": DAY, "tokens": dict(total), "by_model": {m: dict(t) for m, t in tokens.items()},
               "voice": {"chars": chars, "seconds": round(seconds, 1),
                         "tts_calls": tts_calls, "stt_calls": stt_calls,
                         "month_credits": int(credits), "our_credits": int(ours),
                         "quota": quota, "quota_percent": round(pct, 1),
                         "projected_percent": round(proj_pct, 1),
                         "projection_reliable": proj_ok,
                         "source": "api" if el_ok else "local"},
               "elevenlabs": el, "deepgram": dg,
               "sessions": len(sessions)},
        text="\n".join(lines))
except SystemExit:
    pass
except Exception as e:
    out(ok=False, severity="warn", text=f"Витрати недоступні: {e}")
