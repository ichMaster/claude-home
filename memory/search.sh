#!/usr/bin/env bash
# Search past sessions: memory/search.sh "query" [count]
exec "$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/memory/search.py" "$@"
