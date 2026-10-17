#!/usr/bin/env bash
# Пробник: стан самої машини
set -euo pipefail
read -r _ total used free shared cache avail < <(free -m | sed -n 2p)
disk_avail=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
disk_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
load=$(cut -d' ' -f1 /proc/loadavg)
up=$(awk '{printf "%d", $1/86400}' /proc/uptime)
temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
temp=$((temp/1000))
sev=info
[ "$disk_pct" -ge 90 ] && sev=warn
[ "$avail" -lt 800 ] && sev=warn
[ "$disk_pct" -ge 95 ] && sev=alert
python3 -c '
import json,sys
avail,total,dg,dp,load,up,temp,sev = sys.argv[1:9]
print(json.dumps({
 "id":"host","ok":True,"severity":sev,
 "value":{"ram_avail_mb":int(avail),"ram_total_mb":int(total),"disk_avail_gb":int(dg),
          "disk_used_pct":int(dp),"load1":float(load),"uptime_days":int(up),"temp_c":int(temp)},
 "text":f"Машина: диск {dg} ГБ вільно ({dp}% зайнято), памʼять {int(avail)/1024:.1f} ГБ доступно, навантаження {load}, аптайм {up} дн, {temp}°C",
 "ttl":300}, ensure_ascii=False))' "$avail" "$total" "$disk_avail" "$disk_pct" "$load" "$up" "$temp" "$sev"
