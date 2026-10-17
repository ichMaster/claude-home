#!/usr/bin/env bash
# Read a value from config.json / config.local.json in shell scripts:
#   . "$(dirname "$0")/config.sh"; queue=$(conf probes.loe.queue)
conf() {
  local root; root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  "${NOOS_PYTHON:-python3}" -c "
import sys; sys.path.insert(0, '$root')
from noosconf import conf
v = conf('$1')
print('' if v is None else v)"
}
