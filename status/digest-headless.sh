#!/usr/bin/env bash
# Digest produced by a separate headless Claude Code session.
# Disable ONLY the telegram plugin (status/digest-settings.json), not MCP as a whole:
# otherwise the second session hijacks getUpdates and the main one loses incoming
# messages (2026-10-17). The claude.ai connectors stay, and that is how the digest
# sees Gmail and Calendar.
set -uo pipefail
cd "$HOME/claude-home"
part="${1:-ранковий}"
exec claude -p "$(cat status/digest-prompt.md | sed "s/{{ЧАСТИНА}}/$part/")" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash" "mcp__claude_ai_Gmail__search_threads" \
                 "mcp__claude_ai_Google_Calendar__list_events" \
                 "mcp__claude_ai_Google_Calendar__list_calendars" \
  --permission-mode acceptEdits
