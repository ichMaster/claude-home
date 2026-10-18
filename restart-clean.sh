#!/usr/bin/env bash
# Restart the session with an empty context: the conversation is dropped, the system
# prompt is rebuilt from persona.md plus the pinned facts, and files on disk are
# untouched (facts, tasks, change log, memory index all survive).
exec systemd-run --user --unit=noos-restart --collect \
  "$HOME/claude-home/restart-session.sh" --fresh
