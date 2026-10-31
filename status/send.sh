#!/usr/bin/env bash
# Collect probes and send them to Telegram as one message:
#   status/send.sh [--title "text"] [--split] <id> [id...]
# --split sends one message per probe, each with its own voice.
set -uo pipefail
cd "$HOME/claude-home"
title=""; split=0
while true; do
  case "${1:-}" in
    --title) title="$2"; shift 2 ;;
    --split) split=1; shift ;;      # one message per probe instead of one for all
    *) break ;;
  esac
done

if [ "$split" = 1 ]; then
  for id in "$@"; do
    body=$(./status/run.sh "$id" | "$HOME/claude-home/.venv-voice/bin/python" -c "
import json,sys
marks={'alert':'🔴','warn':'🟡','info':'•','quiet':'·'}
for p in json.load(sys.stdin):
    print(marks.get(p.get('severity','info'),'•'), p.get('text',''))")
    [ -n "$body" ] && ./notify.sh --voice "$body"
  done
  exit 0
fi
body=$(./status/run.sh "$@" | "$HOME/claude-home/.venv-voice/bin/python" -c "
import json,sys
marks={'alert':'🔴','warn':'🟡','info':'•','quiet':'·'}
for p in json.load(sys.stdin):
    print(marks.get(p.get('severity','info'),'•'), p.get('text',''))")
[ -n "$title" ] && body="$title

$body"
./notify.sh --voice "$body"
