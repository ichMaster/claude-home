#!/usr/bin/env bash
# Пробник: сесія, таймери, контейнери
set -euo pipefail
tmux_ok=$(tmux has-session -t claude 2>/dev/null && echo 1 || echo 0)
home_ok=$(systemctl --user is-active claude-home 2>/dev/null | grep -qE 'active' && echo 1 || echo 0)
mem_ok=$(systemctl --user is-active claude-memory.timer 2>/dev/null | grep -q active && echo 1 || echo 0)
cnt=$(docker ps -q 2>/dev/null | wc -l)
down=$(docker ps -a --filter 'status=exited' --format '{{.Names}}' 2>/dev/null | tr '\n' ' ')
python3 -c '
import json,sys
t,h,m,c,down = sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),sys.argv[5].strip()
bad=[]
if t!="1": bad.append("tmux-сесія claude не працює")
if h!="1": bad.append("claude-home неактивний")
if m!="1": bad.append("таймер памʼяті зупинений")
if down: bad.append("зупинені контейнери: "+down)
sev = "alert" if t!="1" else ("warn" if bad else "info")
text = "Сервіси: усе працює — сесія, claude-home, таймер памʼяті, контейнерів %d" % c if not bad else "Сервіси: " + "; ".join(bad)
print(json.dumps({"id":"services","ok":not bad,"severity":sev,
 "value":{"tmux":t=="1","claude_home":h=="1","memory_timer":m=="1","containers":c,"exited":down},
 "text":text,"ttl":120}, ensure_ascii=False))' "$tmux_ok" "$home_ok" "$mem_ok" "$cnt" "$down"
