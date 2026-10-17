#!/usr/bin/env bash
# Noos voice reply: voice/reply.sh "text" [out.ogg] [off|light|medium|heavy]
# The filter is off by default — clean voice. Muffling is enabled by the third
# argument or the NOOS_MUFFLE variable.
set -euo pipefail
cd "$HOME/claude-home"
text="$1"
out="${2:-/tmp/noos-reply.ogg}"
preset="${3:-${NOOS_MUFFLE:-off}}"
tmp="$(mktemp --suffix=.mp3)"
./voice/el_say.sh "$tmp" "$text" >/dev/null
if [ "$preset" = off ] || [ "$preset" = none ]; then
  .venv-voice/bin/python voice/to_ogg.py "$tmp" "$out" >/dev/null
else
  .venv-voice/bin/python voice/muffle.py "$tmp" "$out" "$preset" >/dev/null
fi
rm -f "$tmp"
echo "$out"
