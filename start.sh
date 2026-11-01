#!/bin/bash
# Start the always-on Claude Code session with the Telegram channel and Remote Control.
# If claude exits, restart it after 5 seconds.
export PATH="$HOME/.bun/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/claude-home" || exit 1
# System prompt = persona + pinned facts + the permission block (tools/permissions.py,
# t1102: the one machine-readable copy of what may happen without asking)
PROMPT="$(cat "$HOME/claude-home/persona.md")
$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" prompt 2>/dev/null)
$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/tools/permissions.py" prompt 2>/dev/null)"

# A handoff note from restart-summary.sh: the thread of the previous session, carried
# into an otherwise clean context. Consumed once, then archived.
HANDOFF="$HOME/claude-home/memory/handoff.md"
if [ -f "$HANDOFF" ]; then
  PROMPT="$PROMPT

## Естафета з попередньої сесії
$(cat "$HANDOFF")"
  mv "$HANDOFF" "$HOME/claude-home/memory/handoff-last.md"
  echo "естафетну записку підхоплено"
fi
BASE_ARGS=(--remote-control "home" --append-system-prompt "$PROMPT" --channels plugin:telegram@claude-plugins-official --permission-mode auto)

# The session continues the previous conversation by default. restart-clean.sh drops
# a one-shot .fresh flag to start empty instead; it applies to the FIRST run only —
# the continue decision is recomputed on every loop iteration, because reusing the
# fresh ARGS after an in-process crash silently dropped the whole conversation (t1052).
PROJECT_DIR="$HOME/.claude/projects/-home-ich-claude-home"
FRESH=0
if [ -f "$HOME/claude-home/.fresh" ]; then
  rm -f "$HOME/claude-home/.fresh"
  FRESH=1
fi

while true; do
  ARGS=("${BASE_ARGS[@]}")
  if [ "$FRESH" = 1 ]; then
    FRESH=0
    echo "сесія стартує з чистого аркуша"
  elif compgen -G "$PROJECT_DIR/*.jsonl" >/dev/null; then
    # --continue would fail on a machine with no transcripts yet, hence the check
    ARGS+=(--continue)
    echo "сесія продовжує попередній контекст"
  fi
  claude "${ARGS[@]}"
  echo "claude завершився, перезапуск через ${NOOS_RESTART_DELAY:-5} с (Ctrl-C щоб зупинити цикл)"
  sleep "${NOOS_RESTART_DELAY:-5}"
done
