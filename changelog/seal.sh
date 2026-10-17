#!/bin/sh
# Apply append-only (chattr +a) to every daily log file.
# Requires root. Install from a terminal, as root:
#   sudo cp ~/claude-home/changelog/seal.sh /usr/local/sbin/noos-seal-changelog
#   sudo sh -c 'echo "17 * * * * root /usr/local/sbin/noos-seal-changelog" > /etc/cron.d/noos-seal-changelog'
# Noos never does this itself: root and permissions are terminal-only.
HOME_DIR="${NOOS_HOME:-/home/ich/claude-home}"
for f in "$HOME_DIR"/changelog/*.jsonl; do
  [ -f "$f" ] || continue
  lsattr "$f" 2>/dev/null | cut -d' ' -f1 | grep -q a || chattr +a "$f"
done
