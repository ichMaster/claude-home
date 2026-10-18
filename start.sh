#!/bin/bash
# Start the always-on Claude Code session with the Telegram channel and Remote Control.
# If claude exits, restart it after 5 seconds.
export PATH="$HOME/.bun/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/claude-home" || exit 1
# System prompt = persona plus the pinned facts from memory/facts/
PROMPT="$(cat "$HOME/claude-home/persona.md")
$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" prompt 2>/dev/null)"
ARGS=(--remote-control "home" --append-system-prompt "$PROMPT" --channels plugin:telegram@claude-plugins-official --permission-mode auto)

# The session continues the previous conversation by default. restart-clean.sh drops
# a one-shot .fresh flag to start empty instead; it is consumed immediately, so the
# next restart (crash, reboot, timer) goes back to continuing.
PROJECT_DIR="$HOME/.claude/projects/-home-ich-claude-home"
if [ -f "$HOME/claude-home/.fresh" ]; then
  rm -f "$HOME/claude-home/.fresh"
  echo "сесія стартує з чистого аркуша"
elif compgen -G "$PROJECT_DIR/*.jsonl" >/dev/null; then
  # --continue would fail on a machine with no transcripts yet, hence the check
  ARGS+=(--continue)
  echo "сесія продовжує попередній контекст"
fi

while true; do
  claude "${ARGS[@]}"
  echo "claude завершився, перезапуск через 5 с (Ctrl-C щоб зупинити цикл)"; sleep 5
done
