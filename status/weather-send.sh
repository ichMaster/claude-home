#!/usr/bin/env bash
# Weather to Telegram, as its own message rather than a line in the digest:
#   status/weather-send.sh          — what it is like now (probe `weather`)
#   status/weather-send.sh --day    — how the day will move (probe `forecast`)
# Fired by noos-weather.timer every three hours while awake, and by
# noos-weather-day.timer in the morning with --day.
set -uo pipefail
cd "$HOME/claude-home"
if [ "${1:-}" = "--day" ]; then
  NOOS_SENT_KIND=weather-day exec ./status/send.sh forecast
fi
NOOS_SENT_KIND=weather exec ./status/send.sh weather
