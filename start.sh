#!/bin/bash
# Запускає постійну сесію Claude Code з Telegram-каналом і Remote Control.
# Якщо claude завершиться — перезапускається через 5 с.
export PATH="$HOME/.bun/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/claude-home" || exit 1
# Системна підказка = персона + закріплені факти з memory/facts/
PROMPT="$(cat "$HOME/claude-home/persona.md")
$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" prompt 2>/dev/null)"
ARGS=(--remote-control "home" --append-system-prompt "$PROMPT" --channels plugin:telegram@claude-plugins-official --permission-mode auto)
while true; do
  claude "${ARGS[@]}"
  echo "claude завершився, перезапуск через 5 с (Ctrl-C щоб зупинити цикл)"; sleep 5
done
