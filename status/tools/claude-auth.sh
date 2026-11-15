# Sourced (not executed) before `claude` runs (t1188). Exports the long-lived
# CLAUDE_CODE_OAUTH_TOKEN only while the regular login is dead: the year token is
# inference-only and would hide the claude.ai connectors and Remote Control.
# The decision is made in Python; this only ever learns the path of the file to source.
unset CLAUDE_CODE_OAUTH_TOKEN
__noos_fb="$("$HOME/claude-home/.venv-voice/bin/python" "$HOME/claude-home/status/tools/claude_auth.py" fallback-file 2>/dev/null)"
if [ -n "$__noos_fb" ] && [ -r "$__noos_fb" ]; then
  set -a; . "$__noos_fb"; set +a
  echo "вхід у Claude закінчився — працюю на запасному токені" >&2
fi
unset __noos_fb
