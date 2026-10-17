#!/usr/bin/env bash
# Run probes with a TTL cache: status/run.sh host loe news:енергетика
# Prints a JSON array, one object per probe.
set -uo pipefail
cd "$HOME/claude-home"
PY="$HOME/claude-home/.venv-voice/bin/python"
mkdir -p status/cache
out=(); now=$(date +%s)

for id in "$@"; do
  cache="status/cache/${id//:/-}.json"
  if [ -f "$cache" ]; then
    age=$(( now - $(stat -c %Y "$cache") ))
    ttl=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1])).get('ttl',300))" "$cache" 2>/dev/null || echo 300)
    if [ "$age" -lt "$ttl" ]; then out+=("$(cat "$cache")"); continue; fi
  fi
  case "$id" in
    news:*) res=$("$PY" status/probes/news.py "${id#news:}" 2>/dev/null) ;;
    host|services) res=$("./status/probes/$id.sh" 2>/dev/null) ;;
    *) res=$("$PY" "status/probes/$id.py" 2>/dev/null) ;;
  esac
  [ -z "$res" ] && res="{\"id\":\"$id\",\"ok\":false,\"severity\":\"warn\",\"text\":\"Пробник $id не відповів\",\"ttl\":60}"
  echo "$res" > "$cache"
  out+=("$res")
done

printf '%s\n' "${out[@]}" | "$PY" -c "
import json,sys
print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()], ensure_ascii=False, indent=1))"
