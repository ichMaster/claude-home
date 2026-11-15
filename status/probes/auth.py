#!/usr/bin/env python
"""Probe: has the always-on session lost its Claude login? (t1187)

On 2026-11-15 the session answered every Telegram message with `Login expired · Please run
/login` in the tmux pane, which the owner never sees — hours of silence with nothing to say
why. This reads the pane and goes `alert` when its latest event is an auth error; the watcher
then delivers it through notify.sh, which talks to the Bot API directly, because Claude is
exactly what is down.

No tmux session means unknown, not expired: that alarm belongs to the `services` probe.
"""
import json, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from authcheck import pane_expired  # type: ignore
import claude_auth  # type: ignore

SESSION = conf("probes.auth.session", "claude")

TEXT = ("Ноос не відповідає: у сесії закінчився вхід у Claude (Login expired). "
        "Повідомлення доходять, але жодне не отримає відповіді, доки не увійдеш знову. "
        f"Як полагодити: ssh на сервер → tmux attach -t {SESSION} → /login, "
        "пройди вхід за посиланням, потім Ctrl-B D, щоб від'єднатися.")
VOICE = ("Ноос не відповідає: у сесії закінчився вхід у Клод. Повідомлення доходять, "
         "але відповідей не буде, доки не увійдеш знову. Зайди на сервер, приєднайся до "
         "сесії тімакс з назвою клод і введи команду логін.")


def capture():
    """The tail of the pane, or None when there is no session to read."""
    lines = int(conf("probes.auth.lines", 80))
    try:
        res = subprocess.run(["tmux", "capture-pane", "-p", "-t", SESSION, "-S", f"-{lines}"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
          "вересня", "жовтня", "листопада", "грудня"]


def expiry(creds_path=None, fallback_path=None, now=None):
    """A warn probe when the login is dead (the session runs on the fallback token, or on
    nothing) or dies within `warn_days`; None while it is healthy (t1188)."""
    now = now or datetime.now()
    st = claude_auth.login_state(creds_path, now)
    ttl = conf("probes.auth.ttl", 60)
    if st["alive"]:
        exp = st["expires"]
        if not exp or exp - now > timedelta(days=int(conf("probes.auth.warn_days", 3))):
            return None
        day = f"{exp.day} {MONTHS[exp.month - 1]}"
        return {"id": "auth", "ok": True, "severity": "warn",
                "value": {"expired": False, "expires": exp.isoformat(timespec="minutes")},
                "text": f"Вхід у Claude закінчиться {day} о {exp:%H:%M}. "
                        f"Онови заздалегідь: tmux attach -t {SESSION} → /login.",
                "voice": f"Вхід у Клод закінчиться {day}. Онови його заздалегідь "
                         "командою логін у сесії клод.",
                "ttl": ttl}
    spare = claude_auth.fallback_file(creds_path, fallback_path, now) is not None
    state = ("працюю на запасному токені: відповідаю, але без пошти, календаря й Remote Control"
             if spare else "запасного токена немає, тож Ноос мовчить")
    spoken = ("працюю на запасному токені, але без пошти й календаря" if spare
              else "запасного токена немає")
    return {"id": "auth", "ok": False, "severity": "warn",
            "value": {"expired": True, "fallback": spare},
            "text": f"Вхід у Claude закінчився — {state}. "
                    f"Полагодити: tmux attach -t {SESSION} → /login.",
            "voice": f"Вхід у Клод закінчився, {spoken}. Увійди знову командою логін у сесії клод.",
            "ttl": ttl}


def probe(pane=None, creds_path=None, fallback_path=None, now=None):
    pane = capture() if pane is None else pane
    ttl = conf("probes.auth.ttl", 60)
    if pane is None:
        return {"id": "auth", "ok": True, "severity": "info", "value": {"expired": None},
                "text": "Вхід у Claude: сесію не видно, перевірити не можу", "ttl": ttl}
    if pane_expired(pane):
        return {"id": "auth", "ok": False, "severity": "alert", "value": {"expired": True},
                "text": TEXT, "voice": VOICE, "ttl": ttl}
    return expiry(creds_path, fallback_path, now) or {
        "id": "auth", "ok": True, "severity": "info", "value": {"expired": False},
        "text": "Вхід у Claude: усе гаразд", "ttl": ttl}


if __name__ == "__main__":
    print(json.dumps(probe(), ensure_ascii=False))
