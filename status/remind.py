#!/usr/bin/env python
"""Nudge around planned blocks: a warning before, a check-in after.

Runs every few minutes from a timer. For every event booked in the `Noos` calendar
(the task log is the source — see tasks/store.py):

  * `lead_min` before the start → a heads-up, so the block does not arrive unnoticed;
  * `checkin_min` after the start → one question: is it going to plan? A "no" is the
    interesting answer — the session then proposes how to replan.

State is `status/state/reminders.json`, keyed by event id plus kind, so nothing is sent
twice. The sleep window from `tasks.sleep` is respected: no nudges while asleep.
"""
import json, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import atomic_write_text, conf, path

HOME = path("paths.home")
STATE = HOME / "status" / "state" / "reminders.json"
LEAD = conf("tasks.reminders.lead_min", 15)
CHECKIN = conf("tasks.reminders.checkin_min", 15)
WINDOW = conf("tasks.reminders.window_min", 6)     # how wide a tick counts as "now"
SLEEP_FROM = conf("tasks.sleep.від", "00:00")
SLEEP_TO = conf("tasks.sleep.до", "08:00")

sys.path.insert(0, str(HOME / "tasks"))
from store import state as task_state          # noqa: E402


def asleep(now):
    h = now.strftime("%H:%M")
    return SLEEP_FROM <= h < SLEEP_TO if SLEEP_FROM < SLEEP_TO else (h >= SLEEP_FROM or h < SLEEP_TO)


def notify(text):
    subprocess.run([str(HOME / "notify.sh"), text], capture_output=True, text=True)


def load_sent():
    """Torn state (the file is rewritten every 5 minutes, outages are routine) must not stop
    reminders forever; at worst a nudge repeats once (t1050)."""
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main():
    now = datetime.now()
    if asleep(now):
        print("сон — не турбую")
        return

    sent = load_sent()
    fresh = {k: v for k, v in sent.items() if v >= (now - timedelta(days=2)).isoformat()}

    for tid, t in task_state().items():
        if t.get("status") != "open":
            continue
        for e in t.get("events") or []:
            start_raw = e.get("start", "")
            if len(start_raw) <= 10:             # all-day mirror, nothing to nudge about
                continue
            try:
                start = datetime.fromisoformat(start_raw)
            except ValueError:
                continue
            if start.tzinfo:
                start = start.replace(tzinfo=None)

            lead_at = start - timedelta(minutes=LEAD)
            check_at = start + timedelta(minutes=CHECKIN)
            end = e.get("end", "")

            key_lead = f"{e['event']}:lead"
            if key_lead not in fresh and lead_at <= now < lead_at + timedelta(minutes=WINDOW):
                tail = f" до {end[11:16]}" if len(end) > 10 else ""
                notify(f"⏰ За {LEAD} хв: {t['title']}\n{start:%H:%M}{tail}")
                fresh[key_lead] = now.isoformat(timespec="seconds")

            key_check = f"{e['event']}:checkin"
            if key_check not in fresh and check_at <= now < check_at + timedelta(minutes=WINDOW):
                notify(f"Минуло {CHECKIN} хв від «{t['title']}». Усе за планом?\n"
                       f"Якщо ні — скажи, що заважає, і я перепланую решту дня.")
                fresh[key_check] = now.isoformat(timespec="seconds")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(STATE, json.dumps(fresh, ensure_ascii=False, indent=1))
    print(f"нагадувань у пам'яті: {len(fresh)}")


if __name__ == "__main__":
    main()
