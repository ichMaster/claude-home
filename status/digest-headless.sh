#!/usr/bin/env bash
# Дайджест окремою headless-сесією Claude Code.
# Вимикаємо САМЕ telegram-плагін (status/digest-settings.json), а не весь MCP:
# інакше друга сесія перехоплює getUpdates і основна втрачає вхідні (17.10.2026).
# Решта конекторів claude.ai лишається — завдяки їм дайджест бачить Gmail і Календар.
set -uo pipefail
cd "$HOME/claude-home"
part="${1:-ранковий}"
exec claude -p "$(cat status/digest-prompt.md | sed "s/{{ЧАСТИНА}}/$part/")" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash" "mcp__claude_ai_Gmail__search_threads" \
                 "mcp__claude_ai_Google_Calendar__list_events" \
                 "mcp__claude_ai_Google_Calendar__list_calendars" \
  --permission-mode acceptEdits
