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
import json, os, signal, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import atomic_write_text, conf, path

HOME = path("paths.home")
STATE = HOME / "status" / "state" / "watch.json"
# `auth` (t1187): a lost Claude login is otherwise silent — the session is alive and mute
DEFAULT_PROBES = ["alarm", "loe", "host", "services", "auth"]
PROBES = sys.argv[1:] or DEFAULT_PROBES
REMIND_AFTER = conf("watch.remind_after_sec", 3 * 3600)  # reminder for a lasting alert
PROBE_TIMEOUT = conf("watch.probe_timeout_sec", 300)     # a wedged probe must not hang the run
NOTIFY_TIMEOUT = conf("watch.notify_timeout_sec", 180)


def run_bounded(cmd, timeout):
    """(returncode, stdout) — or None when the command did not finish in time.

    The whole process group dies on timeout (t1201): killing the shell alone leaves a
    wedged grandchild (docker ps, tmux) holding the inherited stdout pipe, and the
    follow-up communicate() would block on it forever — which is exactly how one stuck
    daemon used to stop all alerting until someone killed the oneshot by hand."""
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return None

def signature(p):
    """What counts as a change — one rule per probe."""
    v = p.get("value") or {}
    pid = p.get("id", "")
    if pid == "loe":
        return f"{v.get('schedule')}|{v.get('updated')}"
    if pid == "alarm":
        # the level too: a yellow→red escalation used to read as "no change" and stay
        # silent until the 3-hour reminder (t1222)
        return f"{v.get('district_alert')}|{v.get('region_alert')}|{v.get('level')}"
    if pid == "host":
        # do not twitch on every percent, only on tens
        return f"{(v.get('disk_used_pct') or 0)//10}|{p.get('severity')}"
    if pid == "services":
        return json.dumps({k: v.get(k) for k in ("tmux", "claude_home", "memory_timer", "exited")},
                          ensure_ascii=False)
    if pid.startswith("news:"):
        return str(len((v.get("items") or [])))
    return p.get("text", "")[:120]

def load_state():
    """Torn state (kill mid-write) must not stop the watcher forever — alerts matter more
    than one run's dedup memory (t1046)."""
    try:
        return json.loads(STATE.read_text()) if STATE.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(STATE, json.dumps(st, ensure_ascii=False, indent=1))


def main():
    res = run_bounded([HOME / "status" / "run.sh", *PROBES], PROBE_TIMEOUT)
    if res is None:
        print(f"run.sh не відповів за {PROBE_TIMEOUT} с — стан не чіпаю")
        return
    raw = res[1]
    try:
        probes = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        probes = []
    # run.sh always emits one entry per probe, so an empty list means it died — saving the
    # empty newstate would wipe every signature and re-send every active warn (t1168)
    if not probes:
        print("run.sh нічого не повернув — стан не чіпаю")
        return

    state = load_state()
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

    if not send:
        save_state(newstate)
        print("тихо")
        return

    body = "\n".join(f"{mark} {p.get('text','')}" for mark, p in send)
    voice = any(p.get("severity") == "alert" for _, p in send)
    # a probe may carry a `voice` copy without Latin script, which the synthesizer mangles
    # (t1187: the login fix names ssh, tmux and /login)
    spoken = "\n".join(p.get("voice") or p.get("text", "") for _, p in send)
    cmd = [str(HOME / "notify.sh")] + (["--voice"] if voice else [])
    if any(p.get("voice") for _, p in send):
        cmd += ["--voice-text", spoken]
    cmd.append(body)
    # state is persisted only after a delivered send: warn fires on signature change alone,
    # so recording an undelivered one would silence that alert forever (t1046)
    sent_res = run_bounded(cmd, NOTIFY_TIMEOUT)
    if sent_res is not None and sent_res[0] == 0:
        save_state(newstate)
    else:
        print("notify.sh не вдався — стан не записую, повторю наступного разу")
    print(body)


if __name__ == "__main__":
    main()
