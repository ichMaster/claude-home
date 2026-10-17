#!/usr/bin/env bash
# Голосова відповідь Нооса: voice/reply.sh "текст" [вихід.ogg] [off|light|medium|heavy]
# За замовчуванням фільтр вимкнений — чистий голос. Приглушення вмикається
# третім аргументом або змінною NOOS_MUFFLE.
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
