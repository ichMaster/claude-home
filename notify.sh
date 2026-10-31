#!/usr/bin/env bash
# Send a Telegram message straight through the Bot API, with no session involved.
#   notify.sh "text"             — text only
#   notify.sh --voice "text"     — text plus a native voice message (ElevenLabs)
#   notify.sh --quiet "text"     — delivered without a notification ping
set -euo pipefail
cd "$HOME/claude-home"
cfg="$HOME/claude-home/.env.telegram"
[ -f "$cfg" ] || { echo "немає $cfg" >&2; exit 1; }
set -a; . "$cfg"; set +a

voice=0; text_only=1; silent=""
case "${1:-}" in
  --quiet)      silent="-d disable_notification=true"; shift ;;   # delivered, no ping
  --voice)      voice=1; shift ;;                # text plus a voice message
  --voice-only) voice=1; text_only=0; shift ;;   # voice only, no text part
esac
text="$*"

# Telegram refuses anything over 4096 characters, so split on paragraph breaks
# and send the parts in order. One long digest used to fail silently with a 400.
if [ "$text_only" = 1 ]; then
mapfile -d '' -t parts < <(printf '%s' "$text" | "$HOME/claude-home/.venv-voice/bin/python" -c '
import sys
LIMIT = 3900
text, out, cur = sys.stdin.read(), [], ""
for block in text.split("\n\n"):
    if len(cur) + len(block) + 2 > LIMIT and cur:
        out.append(cur); cur = ""
    cur += ("\n\n" if cur else "") + block
    while len(cur) > LIMIT:                       # a single oversized paragraph
        out.append(cur[:LIMIT]); cur = cur[LIMIT:]
if cur:
    out.append(cur)
sys.stdout.write("\0".join(out))')

for part in "${parts[@]}"; do
  [ -z "$part" ] && continue
  curl -sS -m 25 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" $silent --data-urlencode "text=$part" -o /dev/null -w 'текст %{http_code}\n'
done
fi

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
