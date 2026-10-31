#!/usr/bin/env bash
# Short daily change summary to Telegram. Bypasses the run.sh cache, always fresh.
#   status/changes-send.sh [YYYY-MM-DD]
set -uo pipefail
cd "$HOME/claude-home"

# The daily copy of the precious files nothing rewrites — the task log, the facts
# (t1080). Hitching it to a timer that already runs every night beats a unit of its own
# for a job that takes a second; the hash check means an unchanged file costs nothing.
"$HOME/claude-home/.venv-voice/bin/python" tools/versions.py snapshot >/dev/null 2>&1 || true

body=$("$HOME/claude-home/.venv-voice/bin/python" status/probes/changes.py "${1:-}" \
  | "$HOME/claude-home/.venv-voice/bin/python" -c "import json,sys; print(json.load(sys.stdin)['text'])")
[ -z "$body" ] && exit 0
./notify.sh "📝 $body"
