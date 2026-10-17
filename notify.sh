#!/usr/bin/env bash
# Send a Telegram message straight through the Bot API, with no session involved.
#   notify.sh "text"             — text only
#   notify.sh --voice "text"     — text plus a native voice message (ElevenLabs)
set -euo pipefail
cd "$HOME/claude-home"
cfg="$HOME/claude-home/.env.telegram"
[ -f "$cfg" ] || { echo "немає $cfg" >&2; exit 1; }
set -a; . "$cfg"; set +a

voice=0
if [ "${1:-}" = "--voice" ]; then voice=1; shift; fi
text="$*"

curl -sS -m 25 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$text" -o /dev/null -w 'текст %{http_code}\n'

[ "$voice" = 1 ] || exit 0

# for synthesis: strip emoji, bullets and links — they sound like garbage
spoken=$(printf '%s' "$text" | "$HOME/claude-home/.venv-voice/bin/python" -c '
import sys, re
t = sys.stdin.read()
t = re.sub(r"https?://\S+", "", t)
t = re.sub(r"[•·🔴🟡⚡📌*_`#]", "", t)
t = re.sub(r"[ \t]+", " ", t)
print("\n".join(x.strip() for x in t.splitlines() if x.strip()))')

mp3=$(mktemp --suffix=.mp3); ogg=$(mktemp --suffix=.ogg)
trap 'rm -f "$mp3" "$ogg"' EXIT
./voice/el_say.sh "$mp3" "$spoken" >/dev/null
.venv-voice/bin/python voice/to_ogg.py "$mp3" "$ogg" >/dev/null
curl -sS -m 60 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendVoice" \
  -F "chat_id=${TELEGRAM_CHAT_ID}" -F "voice=@${ogg}" -o /dev/null -w 'голос %{http_code}\n'
