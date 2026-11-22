#!/usr/bin/env bash
# Read a value from config.json / config.local.json in shell scripts:
#   . "$(dirname "$0")/config.sh"; queue=$(conf probes.loe.queue)
conf() {
  local root; root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # the key and root go in as argv, never into the source (t1231)
  "${NOOS_PYTHON:-python3}" -c "
import sys; sys.path.insert(0, sys.argv[2])
from noosconf import conf
v = conf(sys.argv[1])
print('' if v is None else v)" "$1" "$root"
}
