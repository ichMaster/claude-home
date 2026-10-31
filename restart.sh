#!/usr/bin/env bash
# The default restart: a handoff note instead of the whole conversation.
# memory/handoff.py writes what we are doing, what was just done and what is open;
# the next session starts clean with that note in its system prompt.
#   restart-continue.sh  keeps everything (expensive)
#   restart-clean.sh     keeps nothing
exec systemd-run --user --unit=noos-restart --collect \
  "$HOME/claude-home/restart-session.sh" --summary
