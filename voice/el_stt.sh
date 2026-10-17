#!/usr/bin/env bash
# Recognition via ElevenLabs Scribe: voice/el_stt.sh <file.oga> [language]
set -euo pipefail
cfg="$HOME/claude-home/.env.voice"
[ -f "$cfg" ] || { echo "немає $cfg (потрібен ELEVENLABS_API_KEY)" >&2; exit 1; }
set -a; . "$cfg"; set +a
f="$1"; lang="${2:-ukr}"
resp=$(curl -sS -X POST 'https://api.elevenlabs.io/v1/speech-to-text' \
  -H "xi-api-key: ${ELEVENLABS_API_KEY}" \
  -F "file=@${f}" -F 'model_id=scribe_v1' -F "language_code=${lang}")
python3 -c '
import json,sys
d=json.loads(sys.stdin.read())
print(d.get("text") or json.dumps(d, ensure_ascii=False)[:400])
' <<<"$resp"
