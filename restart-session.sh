#!/usr/bin/env bash
# Restart the always-on session from outside its own cgroup and report to Telegram.
#   restart-session.sh --continue   keep the conversation (the default)
#   restart-session.sh --fresh      start with an empty context
# Not meant to be called directly — use restart.sh or restart-clean.sh, which detach
# it with systemd-run so the restart survives the death of the calling session.
set -uo pipefail
mode="${1:---continue}"
cd "$HOME/claude-home"

if [ "$mode" = "--fresh" ]; then
  touch "$HOME/claude-home/.fresh"
  what="з чистого аркуша"
else
  rm -f "$HOME/claude-home/.fresh"
  what="з контекстом"
fi

sleep 3
systemctl --user restart claude-home
sleep 30

if pgrep -u "$USER" -f "claude --remote-control home" >/dev/null; then
  facts=$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" list 2>/dev/null | tail -1)
  "$HOME/claude-home/notify.sh" "Сесія перезапущена $what. $facts — у системній підказці. — Ноос"
else
  "$HOME/claude-home/notify.sh" "Перезапуск не вдався: процес claude не піднявся. Глянь tmux attach -t claude. — Ноос"
fi
