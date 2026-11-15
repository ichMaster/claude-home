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
. "$HOME/claude-home/status/tools/claude-auth.sh"   # t1188: year token only if the login is dead
# Label this session's messages in the Sent log: the sender here is a model, so notify.sh
# cannot read a script name out of the process tree (t1121).
export NOOS_SENT_KIND="code-review-headless.sh"
# The review runs an ultracode Workflow, whose agents live in the background of this
# session. `claude -p` waits for background tasks only up to its print-mode ceiling — 600 s
# by default — and then terminates them and exits cleanly: eight nights in a row (3-10
# November 2026) died mid fan-out with no report written and `status=0/SUCCESS` in the
# journal. Zero means wait; the unit's TimeoutStartSec=3600 is what bounds the run (t1142).
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0
model="$("$HOME/claude-home/.venv-voice/bin/python" -c "
import sys; sys.path.insert(0,'$HOME/claude-home')
from noosconf import conf
print(conf('codereview.model','claude-fable-5'))")"
claude -p "$(cat status/code-review-prompt.md)" \
  --model "$model" \
  --settings "$HOME/claude-home/status/digest-settings.json" \
  --allowedTools "Bash" "Read" "Edit" "Write" "Grep" "Glob" "Workflow" "Task" "Agent" \
  --permission-mode acceptEdits
status=$?

# A review that wrote no scan report did nothing, whatever its exit code says. Without this
# check the service reported success for every one of those eight nights and the gap only
# showed up when someone listed the report directory by hand. Today's report, not any
# report: a stale file from an earlier day would hide the very first broken night.
report="status/state/code-review/$(date +%F)-scan.md"
if [ ! -s "$report" ]; then
  ./notify.sh --quiet \
    "Нічне ревʼю не записало звіт — сесія завершилась із кодом $status, файл $report відсутній."
  exit 1
fi
exit "$status"
