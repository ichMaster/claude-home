#!/usr/bin/env bash
# Collect probes and send them to Telegram as one message:
#   status/send.sh [--title "text"] <id> [id...]
set -uo pipefail
cd "$HOME/claude-home"
title=""
if [ "${1:-}" = "--title" ]; then title="$2"; shift 2; fi
body=$(./status/run.sh "$@" | "$HOME/claude-home/.venv-voice/bin/python" -c "
import json,sys
marks={'alert':'🔴','warn':'🟡','info':'•','quiet':'·'}
for p in json.load(sys.stdin):
    print(marks.get(p.get('severity','info'),'•'), p.get('text',''))")
[ -n "$title" ] && body="$title

$body"
./notify.sh --voice "$body"
