#!/usr/bin/env bash
# Nightly self code-review in a separate headless session, right after the 05:00 restart.
# Fable 5 model, ultracode multi-agent review; fixes High/Medium findings locally (never
# pushes), writes two reports (scan, then fix results) and quiet Telegram summaries. The
# owner asked for this 2026-10-31.
#
# The telegram plugin is disabled (status/digest-settings.json) so this session does not
# hijack getUpdates from the main one. Reports live under status/state/code-review/, which is
# git-ignored, so they never go to the public repo. Fixes are committed locally; a push waits
# for the owner's morning approval (see CLAUDE.md § Git).
set -uo pipefail
cd "$HOME/claude-home"
# Label this session's messages in the Sent log: the sender here is a model, so notify.sh
# cannot read a script name out of the process tree (t1121).
export NOOS_SENT_KIND="code-review-headless.sh"
model="$("$HOME/claude-home/.venv-voice/bin/python" -c "
import sys; sys.path.insert(0,'$HOME/claude-home')
from noosconf import conf
print(conf('codereview.model','claude-fable-5'))")"
exec claude -p "$(cat status/code-review-prompt.md)" \
  --model "$model" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash" "Read" "Edit" "Write" "Grep" "Glob" "Workflow" "Task" "Agent" \
  --permission-mode acceptEdits
