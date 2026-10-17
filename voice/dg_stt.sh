#!/usr/bin/env bash
# Recognition via Deepgram: voice/dg_stt.sh <file.oga> [language] [model]
set -euo pipefail
cfg="$HOME/claude-home/.env.voice"
[ -f "$cfg" ] || { echo "немає $cfg (потрібен DEEPGRAM_API_KEY)" >&2; exit 1; }
set -a; . "$cfg"; set +a
f="$1"; lang="${2:-uk}"; model="${3:-${DEEPGRAM_MODEL:-nova-2}}"

# Deepgram drops the first word when speech starts immediately — pad with silence
padded="$(mktemp --suffix=.ogg)"
if "$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/voice/pad.py" "$f" "$padded" 0.6 >/dev/null 2>&1; then
  src="$padded"
else
  src="$f"
fi
trap 'rm -f "$padded"' EXIT
resp=$(curl -sS -X POST \
  "https://api.deepgram.com/v1/listen?model=${model}&language=${lang}&smart_format=true&punctuate=true" \
  -H "Authorization: Token ${DEEPGRAM_API_KEY}" \
  -H 'Content-Type: audio/ogg' \
  --data-binary @"$src")
txt=$(python3 -c '
import json,sys
d=json.loads(sys.stdin.read())
try:
    print(d["results"]["channels"][0]["alternatives"][0]["transcript"])
except Exception:
    print(json.dumps(d, ensure_ascii=False)[:500], file=sys.stderr); sys.exit(1)
' <<<"$resp")

# Deepgram sometimes returns nothing on very short clips — fall back to ElevenLabs Scribe
if [ -z "${txt// /}" ]; then
  echo "Deepgram повернув порожньо, пробую Scribe" >&2
  "$HOME/claude-home/voice/el_stt.sh" "$f" ukr
else
  echo "$txt"
fi
