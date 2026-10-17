#!/usr/bin/env bash
# Short daily change summary to Telegram. Bypasses the run.sh cache, always fresh.
#   status/changes-send.sh [YYYY-MM-DD]
set -uo pipefail
cd "$HOME/claude-home"
body=$("$HOME/claude-home/.venv-voice/bin/python" status/probes/changes.py "${1:-}" \
  | "$HOME/claude-home/.venv-voice/bin/python" -c "import json,sys; print(json.load(sys.stdin)['text'])")
[ -z "$body" ] && exit 0
./notify.sh "📝 $body"
