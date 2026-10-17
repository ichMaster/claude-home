#!/usr/bin/env bash
# Пошук по минулих сесіях: memory/search.sh "запит" [скільки]
exec "$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/search.py" "$@"
