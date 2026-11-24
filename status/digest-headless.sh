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
# The timer fires at 08:03 and 20:03 with no argument, so the part comes from the clock —
# the unit used to hardcode вечірній and the designed morning digest never ran (t1203).
# An explicit argument still wins: the /digest command passes the part by hand.
# NOOS_DIGEST_HOUR pins the hour in tests.
part="${1:-}"
if [ -z "$part" ]; then
  . "$HOME/claude-home/config.sh"
  until_h=$(NOOS_PYTHON="$HOME/claude-home/.venv-voice/bin/python" conf digest.morning_until_hour)
  hour=$((10#${NOOS_DIGEST_HOUR:-$(date +%H)}))
  if [ "$hour" -lt "${until_h:-14}" ]; then part="ранковий"; else part="вечірній"; fi
fi
# Bash rules name command prefixes, never bare "Bash": this session reads inbound mail —
# text anyone on the internet can write — and an allowlist of everything turns a prompt
# injection into arbitrary command execution (t1186). Only what the prompt prescribes;
# no bare python (-c would be arbitrary code again). No cat/head/tail — they reach the
# .env files — and no Write/Edit: acceptEdits reopened the same injection one step
# removed, through a file a trusted session later obeys (t1207).
exec claude -p "$(cat status/digest-prompt.md | sed "s/{{ЧАСТИНА}}/$part/")" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash(./status/run.sh:*)" "Bash(./notify.sh:*)" \
                 "Bash(.venv-voice/bin/python status/candidates.py:*)" \
                 "Bash(.venv-voice/bin/python status/tools/news_seen.py:*)" \
                 "Bash(.venv-voice/bin/python tasks/store.py list:*)" \
                 "Bash(date:*)" \
                 "mcp__claude_ai_Gmail__search_threads" \
                 "mcp__claude_ai_Google_Calendar__list_events" \
                 "mcp__claude_ai_Google_Calendar__list_calendars" \
  --disallowedTools "Write" "Edit" "MultiEdit" "NotebookEdit"
