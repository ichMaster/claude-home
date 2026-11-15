#!/usr/bin/env bash
# The daily YouTube digest in a separate headless session: drains what the probe
# accumulated over the day, picks a handful worth watching and sends them to Telegram.
# The telegram plugin stays disabled so this session does not steal getUpdates.
set -uo pipefail
cd "$HOME/claude-home"
. "$HOME/claude-home/status/tools/claude-auth.sh"   # t1188: year token only if the login is dead
# Label this session's messages in the Sent log: the sender here is a model, so notify.sh
# cannot read a script name out of the process tree (t1121).
export NOOS_SENT_KIND="youtube-headless.sh"
# Prefix rules, never bare "Bash": RSS titles from 600 channels are foreign text, and an
# allowlist of everything turns a prompt injection into command execution (t1186).
exec claude -p "$(cat status/youtube-prompt.md)" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash(./notify.sh:*)" \
                 "Bash(.venv-voice/bin/python status/probes/youtube.py:*)" \
                 "Bash(cat:*)" "Bash(echo:*)" "Bash(date:*)" \
                 "Bash(head:*)" "Bash(tail:*)" \
  --permission-mode acceptEdits
