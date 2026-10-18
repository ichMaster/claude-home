#!/usr/bin/env bash
# Social check in a separate headless session: YouTube probe plus Facebook mail
# through the Gmail connector. Sends to Telegram only when there is something.
# The telegram plugin is disabled (status/digest-settings.json) so this session
# does not steal getUpdates from the main one.
set -uo pipefail
cd "$HOME/claude-home"
exec claude -p "$(cat status/social-prompt.md)" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash" "mcp__claude_ai_Gmail__search_threads" \
  --permission-mode acceptEdits
