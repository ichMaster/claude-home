#!/usr/bin/env bash
# Social check in a separate headless session: YouTube probe plus Facebook mail
# through the Gmail connector. Sends to Telegram only when there is something.
# The telegram plugin is disabled (status/digest-settings.json) so this session
# does not steal getUpdates from the main one.
set -uo pipefail
cd "$HOME/claude-home"
. "$HOME/claude-home/status/tools/claude-auth.sh"   # t1188: year token only if the login is dead
# Label this session's messages in the Sent log: the sender here is a model, so notify.sh
# cannot read a script name out of the process tree (t1121).
export NOOS_SENT_KIND="social-headless.sh"
# Prefix rules, never bare "Bash": this session reads facebookmail bodies — foreign text —
# and an allowlist of everything turns a prompt injection into command execution (t1186).
# No cat/head/tail (they reach the .env files) and no Write/Edit: acceptEdits reopened
# the same injection through a file a trusted session later obeys (t1207).
exec claude -p "$(cat status/social-prompt.md)" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash(./notify.sh:*)" "Bash(./status/run.sh:*)" \
                 "Bash(.venv-voice/bin/python status/probes/youtube.py:*)" \
                 "Bash(date:*)" \
                 "mcp__claude_ai_Gmail__search_threads" \
  --disallowedTools "Write" "Edit" "MultiEdit" "NotebookEdit"
