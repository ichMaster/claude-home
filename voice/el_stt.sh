#!/usr/bin/env bash
# Recognition via ElevenLabs Scribe: voice/el_stt.sh <file.oga> [language]
set -euo pipefail
cfg="$HOME/claude-home/.env.voice"
[ -f "$cfg" ] || { echo "немає $cfg (потрібен ELEVENLABS_API_KEY)" >&2; exit 1; }
set -a; . "$cfg"; set +a
f="$1"; lang="${2:-ukr}"
resp=$(curl -sS --connect-timeout 10 --max-time 120 -X POST 'https://api.elevenlabs.io/v1/speech-to-text' \
  -H "xi-api-key: ${ELEVENLABS_API_KEY}" \
  -F "file=@${f}" -F 'model_id=scribe_v1' -F "language_code=${lang}")
# A body without "text" is an error (bad key, quota, format) and must go to stderr with a
# non-zero exit — printed to stdout it became the "recognized" text the bots answered
# (t1212). An empty text is an answer: recognized silence, not a failure.
python3 -c '
import json,sys
d=json.loads(sys.stdin.read())
if "text" in d:
    print(d["text"])
else:
    print(json.dumps(d, ensure_ascii=False)[:400], file=sys.stderr)
    sys.exit(1)
' <<<"$resp"
