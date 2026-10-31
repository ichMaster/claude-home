#!/usr/bin/env bash
# Restart the session keeping the whole conversation (claude --continue).
# The expensive option: a long conversation is re-read on every turn afterwards.
# Detached through systemd-run, so it survives the death of the session that called it.
exec systemd-run --user --unit=noos-restart --collect \
  "$HOME/claude-home/restart-session.sh" --continue
