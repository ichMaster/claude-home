#!/usr/bin/env bash
# Send a Telegram message straight through the Bot API, with no session involved.
#   notify.sh "text"             — text plus a native voice message (ElevenLabs)
#   notify.sh --no-voice "text"  — text only (rare: bare link lists, mostly code)
#   notify.sh --voice-only "text"— voice only, no text part
#   notify.sh --quiet "text"     — delivered without a notification ping
#   notify.sh --voice-as <name> "text"
#                                — speak in a named voice from `voice.voices`
#                                  (config.local.json): noos, oren, sergey, lili, …
#   notify.sh --voice-profile <role|profile> "text"
#                                — speak with a whole profile: voice + model + settings
#                                  (`voice.roles` / `voice.profiles`), which is what audio
#                                  tags need — see docs/voice-emotion.md
#   notify.sh --voice-text "spoken" "text"
#                                — the text goes out as written, the voice reads "spoken"
#                                  instead (a long report with a short spoken digest)
#   notify.sh --kind <name> "text"
#                                — label this message in the Sent log (status/state/
#                                  chat-log.jsonl); without it the log records the calling
#                                  script's own name
#   notify.sh --bot <kind> "text"
#                                — send through a named bot from `telegram.bots`
#                                  (config.json): mood, youtube. One-way channels: the
#                                  horoscope and the video picks stop burying the
#                                  conversation in the main chat.
# Voice is the default: the user listens to Telegram rather than reading it, so a
# text-only message is a message they cannot take. Flags may be combined.
set -euo pipefail
cd "$HOME/claude-home"
cfg="$HOME/claude-home/.env.telegram"
[ -f "$cfg" ] || { echo "немає $cfg" >&2; exit 1; }
set -a; . "$cfg"; set +a

voice=1; text_only=1; silent=""; quiet=0; vtext=""; vname=""; vprof=""; bot=""
kind=""; text_code=""; voice_code=""
while true; do
  case "${1:-}" in
    --quiet)      quiet=1; silent="-d disable_notification=true"; shift ;;  # no ping
    --voice)      voice=1; shift ;;                # the default, kept for callers
    --voice-only) voice=1; text_only=0; shift ;;   # voice only, no text part
    --no-voice)   voice=0; shift ;;                # text only
    --voice-text) vtext="${2:-}"; shift 2 ;;       # synthesize this instead of the text
    --voice-as)   vname="${2:-}"; shift 2 ;;       # a named voice from voice.voices
    --voice-profile) vprof="${2:-}"; shift 2 ;;    # a role or profile: voice + model + settings
    --bot)        bot="${2:-}"; shift 2 ;;         # a named bot from telegram.bots
    --kind)       kind="${2:-}"; shift 2 ;;        # what kind of message, for the Sent log
    *) break ;;
  esac
done
text="$*"

# A named bot swaps the token for this message only. Resolved before the first send,
# because the text part goes out before the voice part. A missing token is not fatal:
# the message falls back to the main bot rather than disappearing.
if [ -n "$bot" ]; then
  . "$HOME/claude-home/config.sh"
  suffix=$(NOOS_PYTHON="$HOME/claude-home/.venv-voice/bin/python" conf "telegram.bots.$bot")
  suffix="${suffix//-/_}"
  if [ -z "$suffix" ]; then
    echo "невідомий бот: $bot — шлю через головного" >&2
  else
    tkey="TELEGRAM_BOT_TOKEN_${suffix^^}"; ckey="TELEGRAM_CHAT_ID_${suffix^^}"
    if [ -n "${!tkey:-}" ]; then
      TELEGRAM_BOT_TOKEN="${!tkey}"
      TELEGRAM_CHAT_ID="${!ckey:-$TELEGRAM_CHAT_ID}"
    else
      echo "немає $tkey у .env.telegram — шлю через головного" >&2
    fi
  fi
fi

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
  code=$(curl -sS -m 25 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" $silent --data-urlencode "text=$part" -o /dev/null -w '%{http_code}')
  echo "текст $code"
  # the worst code wins: one part refused means the message did not go out whole
  if [ -z "$text_code" ] || [ "$code" != "200" ]; then text_code="$code"; fi
done
fi

# One line per outgoing message, with Telegram's own answer rather than an assumption
# (t1119). Nothing else in this project knew what had been said.
sent_log() {
  printf '%s' "${text:-${vtext:-}}" | "$HOME/claude-home/.venv-voice/bin/python" \
    "$HOME/claude-home/status/tools/sent_log.py" --bot "${bot:-main}" --kind "$kind" \
    --text-code "$text_code" --voice-code "$voice_code" 2>/dev/null || true
}

if [ "$voice" != 1 ]; then
  sent_log
  exit 0
fi

# for synthesis: strip emoji, bullets and links — they sound like garbage
spoken=$(printf '%s' "${vtext:-$text}" | "$HOME/claude-home/.venv-voice/bin/python" -c '
import sys, re
t = sys.stdin.read()
t = re.sub(r"https?://\S+", "", t)
t = re.sub(r"[•·🔴🟡⚡📌*_`#]", "", t)
t = re.sub(r"[ \t]+", " ", t)
print("\n".join(x.strip() for x in t.splitlines() if x.strip()))')

# a profile sets voice, model and settings for this message only; tags need the v4 model,
# so the profile is the unit, not the voice alone
if [ -n "$vprof" ]; then
  while IFS= read -r line; do [ -n "$line" ] && export "$line"; done < <(
    "$HOME/claude-home/.venv-voice/bin/python" \
      "$HOME/claude-home/status/tools/voice_profile.py" "$vprof")
fi

# a named voice wins over .env.voice for this message only
if [ -n "$vname" ]; then
  . "$HOME/claude-home/config.sh"
  NOOS_PYTHON="$HOME/claude-home/.venv-voice/bin/python"
  vid=$(NOOS_PYTHON="$NOOS_PYTHON" conf "voice.voices.$vname")
  if [ -n "$vid" ]; then export ELEVENLABS_VOICE_ID="$vid"
  else echo "невідомий голос: $vname" >&2; fi
fi

mp3=$(mktemp --suffix=.mp3); ogg=$(mktemp --suffix=.ogg)
trap 'rm -f "$mp3" "$ogg"' EXIT
./voice/el_say.sh "$mp3" "$spoken" >/dev/null
.venv-voice/bin/python voice/to_ogg.py "$mp3" "$ogg" "${NOOS_TEMPO:-1.0}" >/dev/null
vsilent=()
if [ "$quiet" = 1 ]; then vsilent=(-F disable_notification=true); fi
voice_code=$(curl -sS -m 60 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendVoice" \
  -F "chat_id=${TELEGRAM_CHAT_ID}" -F "voice=@${ogg}" "${vsilent[@]}" -o /dev/null -w '%{http_code}')
echo "голос $voice_code"
sent_log
