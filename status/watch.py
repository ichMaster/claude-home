#!/usr/bin/env python
"""Watcher: checks the probes every 15 minutes and speaks only when there is
something to say — a change or a problem.

Rules:
  alert  — sent on every change; if it persists, repeated once every 3 hours
  warn   — sent only when the signature changes (a new outage schedule, say)
  info   — silent; reaches the user only through the full digest
  news   — only topics marked "терміново": true

The signature is what counts as "the same news". If it has not changed, the user is
not disturbed again.
"""
import json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

HOME = path("paths.home")
STATE = HOME / "status" / "state" / "watch.json"
PROBES = sys.argv[1:] or ["alarm", "loe", "host", "services"]
REMIND_AFTER = conf("watch.remind_after_sec", 3 * 3600)  # reminder for a lasting alert

def signature(p):
    """What counts as a change — one rule per probe."""
    v = p.get("value") or {}
    pid = p.get("id", "")
    if pid == "loe":
        return f"{v.get('schedule')}|{v.get('updated')}"
    if pid == "alarm":
        return f"{v.get('district_alert')}|{v.get('region_alert')}"
    if pid == "host":
        # do not twitch on every percent, only on tens
        return f"{(v.get('disk_used_pct') or 0)//10}|{p.get('severity')}"
    if pid == "services":
        return json.dumps({k: v.get(k) for k in ("tmux", "claude_home", "memory_timer", "exited")},
                          ensure_ascii=False)
    if pid.startswith("news:"):
        return str(len((v.get("items") or [])))
    return p.get("text", "")[:120]

raw = subprocess.run([str(HOME / "status" / "run.sh"), *PROBES],
                     capture_output=True, text=True).stdout
probes = json.loads(raw) if raw.strip() else []

state = json.loads(STATE.read_text()) if STATE.exists() else {}
now = time.time()
send, newstate = [], {}

for p in probes:
    pid = p.get("id", "?")
    sev = p.get("severity", "info")
    sig = signature(p)
    prev = state.get(pid, {})
    changed = prev.get("sig") != sig
    stale = now - prev.get("sent", 0) > REMIND_AFTER

    if sev == "alert" and (changed or stale):
        send.append(("🔴", p))
    elif sev == "warn" and changed:
        send.append(("🟡", p))
    elif sev == "info" and changed and prev.get("sev") in ("warn", "alert"):
        send.append(("✅", p))            # повернулось у норму — теж новина

    newstate[pid] = {"sig": sig, "sev": sev,
                     "sent": now if any(x[1] is p for x in send) else prev.get("sent", 0)}

STATE.parent.mkdir(parents=True, exist_ok=True)
STATE.write_text(json.dumps(newstate, ensure_ascii=False, indent=1))

if not send:
    print("тихо")
    sys.exit(0)

body = "\n".join(f"{mark} {p.get('text','')}" for mark, p in send)
voice = any(p.get("severity") == "alert" for _, p in send)
cmd = [str(HOME / "notify.sh")] + (["--voice"] if voice else []) + [body]
subprocess.run(cmd)
print(body)
