#!/bin/bash
# Start the always-on Claude Code session with the Telegram channel and Remote Control.
# If claude exits, restart it after 5 seconds.
export PATH="$HOME/.bun/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/claude-home" || exit 1
# System prompt = persona plus the pinned facts from memory/facts/
PROMPT="$(cat "$HOME/claude-home/persona.md")
$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" prompt 2>/dev/null)"
ARGS=(--remote-control "home" --append-system-prompt "$PROMPT" --channels plugin:telegram@claude-plugins-official --permission-mode auto)
while true; do
  claude "${ARGS[@]}"
  echo "claude завершився, перезапуск через 5 с (Ctrl-C щоб зупинити цикл)"; sleep 5
done
