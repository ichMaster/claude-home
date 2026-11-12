#!/usr/bin/env bash
# Restart the always-on session from outside its own cgroup and report to Telegram.
#   restart-session.sh --summary    clean context plus a handoff note (the default)
#   restart-session.sh --continue   keep the whole conversation
#   restart-session.sh --fresh      start with an empty context
# Not meant to be called directly — use restart.sh or restart-clean.sh, which detach
# it with systemd-run so the restart survives the death of the calling session.
set -uo pipefail
mode="${1:---summary}"
cd "$HOME/claude-home"

# warn in the chat before the session dies, so a restart is never a silent gap
case "$mode" in
  --summary)  warn="Перезапускаюсь. Складаю естафетну записку — контекст розмови зникне, нитка лишиться." ;;
  --continue) warn="Перезапускаюсь зі збереженням усієї розмови. Хвилина тиші." ;;
  --fresh)    warn="Перезапускаюсь з чистого аркуша. Контекст розмови зникне; факти, задачі й журнали лишаються." ;;
esac
# 03:00-08:00 is the sleep window: deliver without a ping
hour=$(date +%H)
quiet=""
if [ "$hour" -ge 3 ] && [ "$hour" -lt 8 ]; then quiet="--quiet"; fi
"$HOME/claude-home/notify.sh" $quiet "$warn — Ноос" >/dev/null 2>&1 || true

note_chars=""
if [ "$mode" = "--summary" ]; then
  # the note must be written before the session dies — it is built from the transcript.
  # Its size is measured here, before start.sh moves the file: the old report read
  # handoff-last.md, which on a failure still held a PREVIOUS restart's note (t1165).
  if "$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/handoff.py" \
       >/tmp/noos-handoff.log 2>&1 && [ -s "$HOME/claude-home/memory/handoff.md" ]; then
    note_chars=$(wc -c < "$HOME/claude-home/memory/handoff.md" | tr -d ' ')
    touch "$HOME/claude-home/.fresh"
    what="з естафетою"
  else
    # no note means a clean start would lose the thread silently — keep the conversation
    # instead, as --continue would (t1165)
    rm -f "$HOME/claude-home/.fresh"
    what="з контекстом: записка не склалась, розмову збережено"
  fi
elif [ "$mode" = "--fresh" ]; then
  touch "$HOME/claude-home/.fresh"
  what="з чистого аркуша"
else
  rm -f "$HOME/claude-home/.fresh"
  what="з контекстом"
fi

sleep 3
systemctl --user restart claude-home
sleep 30

if pgrep -u "$USER" -f "claude --remote-control home" >/dev/null; then
  facts=$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/facts.py" list 2>/dev/null | tail -1)
  note=""
  if [ "$mode" = "--summary" ]; then
    if [ -n "$note_chars" ]; then
      note=" Записка: $note_chars символів."
    else
      note=" Записка не склалась (/tmp/noos-handoff.log)."
    fi
  fi
  "$HOME/claude-home/notify.sh" $quiet "Сесія перезапущена $what.$note $facts — у системній підказці. — Ноос"
else
  "$HOME/claude-home/notify.sh" "Перезапуск не вдався: процес claude не піднявся. Глянь tmux attach -t claude. — Ноос"
fi
