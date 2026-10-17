#!/usr/bin/env bash
# Реєструє меню команд бота (Bot API setMyCommands). Ідемпотентно — перезапис повного списку.
#   telegram/commands.sh          — поставити набір нижче
#   telegram/commands.sh --зняти  — прибрати меню
# Імена команд лише [a-z0-9_]; опис — українською, його видно в меню.
set -euo pipefail
cd "$HOME/claude-home"
set -a; . "$HOME/claude-home/.env.telegram"; set +a
API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"

if [ "${1:-}" = "--зняти" ]; then
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
 {"command":"changes", "description":"Що Ноос змінив за сьогодні"},
 {"command":"digest",  "description":"Зібрати дайджест новин зараз"}
]
JSON

# глобально (усі приватні чати)
curl -sS -m 20 -X POST "$API/setMyCommands" \
  -H "Content-Type: application/json" \
  -d "{\"commands\": $COMMANDS}" | head -c 200; echo

# ще й точково для свого чату — клієнт підхоплює такий список швидше за кеш
curl -sS -m 20 -X POST "$API/setMyCommands" \
  -H "Content-Type: application/json" \
  -d "{\"commands\": $COMMANDS, \"scope\": {\"type\": \"chat\", \"chat_id\": ${TELEGRAM_CHAT_ID}}}" | head -c 200; echo

# кнопка меню замість вкладки веб-застосунку
curl -sS -m 20 -X POST "$API/setChatMenuButton" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": ${TELEGRAM_CHAT_ID}, \"menu_button\": {\"type\": \"commands\"}}" | head -c 200; echo
