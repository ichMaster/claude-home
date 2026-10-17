#!/usr/bin/env bash
# Synthesis via ElevenLabs: voice/el_say.sh <out.mp3> "text"
# Voice and pace are overridable: ELEVENLABS_VOICE_ID, ELEVENLABS_SPEED (0.7-1.2), ELEVENLABS_STABILITY
set -euo pipefail
ov="${ELEVENLABS_VOICE_ID:-}"; osp="${ELEVENLABS_SPEED:-}"; ost="${ELEVENLABS_STABILITY:-}"
cfg="$HOME/claude-home/.env.voice"
[ -f "$cfg" ] || { echo "немає $cfg" >&2; exit 1; }
set -a; . "$cfg"; set +a
[ -n "$ov" ] && ELEVENLABS_VOICE_ID="$ov"
[ -n "$osp" ] && ELEVENLABS_SPEED="$osp"
[ -n "$ost" ] && ELEVENLABS_STABILITY="$ost"
out="$1"; shift
text="$*"
model="${ELEVENLABS_MODEL:-eleven_multilingual_v2}"
speed="${ELEVENLABS_SPEED:-1.1}"
stab="${ELEVENLABS_STABILITY:-0.6}"
body=$(python3 -c '
import json,sys
print(json.dumps({"text":sys.argv[1],"model_id":sys.argv[2],
  "voice_settings":{"stability":float(sys.argv[3]),"similarity_boost":0.75,
                    "style":0.0,"speed":float(sys.argv[4]),"use_speaker_boost":True}}))' \
  "$text" "$model" "$stab" "$speed")
code=$(curl -sS -o "$out" -w '%{http_code}' \
  -X POST "https://api.elevenlabs.io/v1/text-to-speech/${ELEVENLABS_VOICE_ID}?output_format=mp3_44100_128" \
  -H "xi-api-key: ${ELEVENLABS_API_KEY}" -H 'Content-Type: application/json' \
  -d "$body")
[ "$code" = 200 ] || { echo "ElevenLabs TTS помилка $code:" >&2; head -c 400 "$out" >&2; echo >&2; exit 1; }
echo "$out"
