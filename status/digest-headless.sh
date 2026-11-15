#!/usr/bin/env bash
# Digest produced by a separate headless Claude Code session.
# Disable ONLY the telegram plugin (status/digest-settings.json), not MCP as a whole:
# otherwise the second session hijacks getUpdates and the main one loses incoming
# messages (2026-10-17). The claude.ai connectors stay, and that is how the digest
# sees Gmail and Calendar.
set -uo pipefail
cd "$HOME/claude-home"
. "$HOME/claude-home/status/tools/claude-auth.sh"   # t1188: year token only if the login is dead
# Label this session's messages in the Sent log: the sender here is a model, so notify.sh
# cannot read a script name out of the process tree (t1121).
export NOOS_SENT_KIND="digest-headless.sh"
part="${1:-ранковий}"
# Bash rules name command prefixes, never bare "Bash": this session reads inbound mail —
# text anyone on the internet can write — and an allowlist of everything turns a prompt
# injection into arbitrary command execution (t1186). Only what the prompt prescribes,
# plus harmless text helpers; no bare python (-c would be arbitrary code again).
exec claude -p "$(cat status/digest-prompt.md | sed "s/{{ЧАСТИНА}}/$part/")" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash(./status/run.sh:*)" "Bash(./notify.sh:*)" \
                 "Bash(.venv-voice/bin/python status/candidates.py:*)" \
                 "Bash(.venv-voice/bin/python status/tools/news_seen.py:*)" \
                 "Bash(.venv-voice/bin/python tasks/store.py:*)" \
                 "Bash(cat:*)" "Bash(echo:*)" "Bash(date:*)" \
                 "Bash(head:*)" "Bash(tail:*)" \
                 "mcp__claude_ai_Gmail__search_threads" \
                 "mcp__claude_ai_Google_Calendar__list_events" \
                 "mcp__claude_ai_Google_Calendar__list_calendars" \
  --permission-mode acceptEdits
