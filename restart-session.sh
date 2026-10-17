#!/usr/bin/env bash
# Перезапуск постійної сесії ззовні її ж cgroup і доповідь у Telegram.
# Запускати через: systemd-run --user --unit=noos-restart --collect ~/claude-home/restart-session.sh
set -uo pipefail
sleep 3
systemctl --user restart claude-home
sleep 30
if pgrep -u "$USER" -f "claude --remote-control home" >/dev/null; then
  facts=$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" list 2>/dev/null | tail -1)
  "$HOME/claude-home/notify.sh" "Сесія перезапущена. $facts — тепер усі в системній підказці. — Ноос"
else
  "$HOME/claude-home/notify.sh" "Перезапуск не вдався: процес claude не піднявся. Глянь tmux attach -t claude. — Ноос"
fi
