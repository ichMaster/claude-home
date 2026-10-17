#!/usr/bin/env bash
# Повний дайджест: усе, що є, одним повідомленням + голосом.
set -uo pipefail
cd "$HOME/claude-home"
hour=$(date +%H)
name="${NOOS_USER_VOCATIVE:+, $NOOS_USER_VOCATIVE}"
if [ "$hour" -lt 12 ]; then greet="Доброго ранку${name}."; else greet="Добрий вечір${name}."; fi
topics=$(ls status/topics/*.json 2>/dev/null | sed 's|.*/||; s|\.json$||' | sed 's/^/news:/' | tr '\n' ' ')
./status/send.sh --заголовок "$greet Зведення на $(date '+%d.%m, %H:%M')" \
  alarm loe weather host services $topics
