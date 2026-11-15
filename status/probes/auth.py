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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from authcheck import pane_expired  # type: ignore

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


def probe(pane=None):
    pane = capture() if pane is None else pane
    ttl = conf("probes.auth.ttl", 60)
    if pane is None:
        return {"id": "auth", "ok": True, "severity": "info", "value": {"expired": None},
                "text": "Вхід у Claude: сесію не видно, перевірити не можу", "ttl": ttl}
    if pane_expired(pane):
        return {"id": "auth", "ok": False, "severity": "alert", "value": {"expired": True},
                "text": TEXT, "voice": VOICE, "ttl": ttl}
    return {"id": "auth", "ok": True, "severity": "info", "value": {"expired": False},
            "text": "Вхід у Claude: усе гаразд", "ttl": ttl}


if __name__ == "__main__":
    print(json.dumps(probe(), ensure_ascii=False))
