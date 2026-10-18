#!/usr/bin/env bash
# Register the bot command menu (Bot API setMyCommands). Idempotent: the whole list
# is replaced.
#   telegram/commands.sh          — install the set below
#   telegram/commands.sh --remove  — remove the menu
# Command names are [a-z0-9_] only; descriptions are Ukrainian — the user sees them.
set -euo pipefail
cd "$HOME/claude-home"
set -a; . "$HOME/claude-home/.env.telegram"; set +a
API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"

if [ "${1:-}" = "--remove" ]; then
  curl -sS -m 20 -X POST "$API/deleteMyCommands" | head -c 200; echo; exit 0
fi

read -r -d '' COMMANDS <<'JSON' || true
[
 {"command":"power",   "description":"Світло: графік і стан черги 4.1"},
 {"command":"alarm",   "description":"Тривоги по Львівщині"},
 {"command":"weather", "description":"Погода у Львові"},
 {"command":"host",    "description":"Сервер: диск, пам'ять, сервіси"},
 {"command":"status",  "description":"Усе разом одним повідомленням"},
 {"command":"mail",    "description":"Що нового в пошті"},
 {"command":"calendar","description":"Календар: сьогодні і завтра"},
 {"command":"tasks",   "description":"Задачі: відкриті й дедлайни"},
 {"command":"task",    "description":"Додати задачу: /task текст [завтра|на вихідних]"},
 {"command":"done",    "description":"Закрити задачу: /done t003 або частина назви"},
 {"command":"plan",    "description":"Забронювати час: /plan t006 завтра 14:00 90хв"},
 {"command":"unplan",  "description":"Зняти бронь часу: /unplan t006"},
 {"command":"today",   "description":"Сьогодні: події, блоки, задачі"},
 {"command":"youtube", "description":"Нові відео з каналів"},
 {"command":"facebook","description":"Що з Facebook стосується тебе"},
 {"command":"linkedin","description":"LinkedIn: повідомлення й запрошення"},
 {"command":"restart", "description":"Перезапуск сесії, контекст зберігається"},
 {"command":"restart_clean","description":"Перезапуск з чистого аркуша"},
 {"command":"changes", "description":"Що Ноос змінив за сьогодні"},
 {"command":"digest",  "description":"Зібрати дайджест новин зараз"}
]
JSON

# globally (all private chats)
curl -sS -m 20 -X POST "$API/setMyCommands" \
  -H "Content-Type: application/json" \
  -d "{\"commands\": $COMMANDS}" | head -c 200; echo

# and for this chat specifically — clients pick that list up faster than the cache
curl -sS -m 20 -X POST "$API/setMyCommands" \
  -H "Content-Type: application/json" \
  -d "{\"commands\": $COMMANDS, \"scope\": {\"type\": \"chat\", \"chat_id\": ${TELEGRAM_CHAT_ID}}}" | head -c 200; echo

# menu button instead of the web-app tab
curl -sS -m 20 -X POST "$API/setChatMenuButton" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": ${TELEGRAM_CHAT_ID}, \"menu_button\": {\"type\": \"commands\"}}" | head -c 200; echo
