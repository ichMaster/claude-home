#!/bin/sh
# Ставить append-only (chattr +a) на всі денні файли журналу.
# Потребує рута. Встановлювати так (з термінала, під рутом):
#   sudo cp ~/claude-home/changelog/seal.sh /usr/local/sbin/noos-seal-changelog
#   sudo sh -c 'echo "17 * * * * root /usr/local/sbin/noos-seal-changelog" > /etc/cron.d/noos-seal-changelog'
# Сам Ноос цього не робить: рут і права — лише з термінала.
HOME_DIR="${NOOS_HOME:-/home/ich/claude-home}"
for f in "$HOME_DIR"/changelog/*.jsonl; do
  [ -f "$f" ] || continue
  lsattr "$f" 2>/dev/null | cut -d' ' -f1 | grep -q a || chattr +a "$f"
done
