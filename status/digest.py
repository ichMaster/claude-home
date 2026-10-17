#!/usr/bin/env python
"""Дайджест: структурований текст і озвучена версія з розділами.

  status/digest.py            — зібрати й надіслати
  status/digest.py --показати — лише надрукувати, нічого не слати
"""
import json, re, subprocess, sys, datetime
from pathlib import Path
sys.path.insert(0, str(Path.home() / "claude-home" / "status"))
import uk_num as u

HOME = Path.home() / "claude-home"
MONTHS = ["", "січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
          "серпня", "вересня", "жовтня", "листопада", "грудня"]

topics = sorted(p.stem for p in (HOME / "status" / "topics").glob("*.json"))
ids = ["loe", "alarm", "weather", "host", "services"] + [f"news:{t}" for t in topics]
raw = subprocess.run([str(HOME / "status" / "run.sh"), *ids],
                     capture_output=True, text=True).stdout
probes = {p["id"]: p for p in (json.loads(raw) if raw.strip() else [])}

now = datetime.datetime.now()
name = os.environ.get("NOOS_USER_VOCATIVE", "")
greet = ("Доброго ранку" if now.hour < 12 else "Добрий вечір") + (f", {name}" if name else "")
date_say = f"{u.num(now.day)} {MONTHS[now.month]}, {u.hhmm(now.strftime('%H:%M'))}"

text, speech = [], []
text.append(f"*{greet}.* Зведення на {now.strftime('%d.%m, %H:%M')}")
speech.append(f"{greet}. Зведення на {date_say}.")

def section(title, lines_text, lines_speech):
    if not lines_text:
        return
    text.append(f"\n*{title}*\n" + "\n".join(lines_text))
    speech.append(f"\n{title}. " + " ".join(lines_speech))

# — світло —
p = probes.get("loe", {})
v = p.get("value") or {}
iv = v.get("intervals") or []
if iv:
    a, b = iv[0]
    cur = p.get("text", "")
    t = [cur.replace("Світло: ", "").capitalize()]
    s = []
    hm = now.strftime("%H:%M")
    if a <= hm < b:
        left = (datetime.datetime.strptime(b, "%H:%M") -
                datetime.datetime.strptime(hm, "%H:%M")).seconds // 60
        s.append(f"Зараз світла немає. Увімкнуть {u.at_time(b)}, це через {u.minutes(left)}.")
    elif hm < a:
        left = (datetime.datetime.strptime(a, "%H:%M") -
                datetime.datetime.strptime(hm, "%H:%M")).seconds // 60
        s.append(f"Світло вимкнуть {u.at_time(a)}, це через {u.minutes(left)}, і буде відсутнє {u.from_to(a, b)}.")
    else:
        s.append("Сьогоднішні відключення вже минули.")
    s.append(f"Графік на сьогодні: {u.from_to(a, b)}, черга {u.cherga(v.get('cherga',''))}.")
    if v.get("updated"):
        s.append(f"Графік оновлювали {u.at_time(v['updated'])}.")
    section("Світло", t, s)
else:
    section("Світло", ["Відключень на сьогодні не заплановано."],
            ["Відключень на сьогодні не заплановано."])

# — тривоги —
p = probes.get("alarm", {})
v = p.get("value") or {}
if v:
    if v.get("district_alert") or v.get("region_alert"):
        t = [f"🔴 Тривога: {v.get('district') if v.get('district_alert') else v.get('region')}"
             + (f", вже {v.get('since')}" if v.get("since") else "")]
        s = [f"Увага. Повітряна тривога, {v.get('district') if v.get('district_alert') else v.get('region')}."]
    else:
        n = len(v.get("elsewhere") or [])
        t = [f"Тривоги немає. По Україні зараз {n} обл."]
        s = [f"У нас тривоги немає.",
             f"По Україні зараз {u.num(n, fem=True)} {u.plural(n,'область','області','областей')}."]
    section("Тривоги", t, s)

# — погода —
p = probes.get("weather", {})
v = p.get("value") or {}
if v:
    t = [f"{v['now_c']}°C, відчувається {v['feels_c']}°C, {v['desc'].lower()}. "
         f"Удень {v['min_c']}…{v['max_c']}°C, дощ {v['rain_chance']}%"]
    s = [f"У Львові зараз {u.degrees(v['now_c'])}, відчувається як {u.degrees(v['feels_c'])}.",
         f"{v['desc']}.",
         f"Удень від {u.gen(v['min_c'])} до {u.gen(v['max_c'])} градусів.",
         f"Ймовірність дощу {u.percent(v['rain_chance'])}."]
    section("Погода", t, s)

# — сервер —
h, sv = probes.get("host", {}).get("value") or {}, probes.get("services", {}).get("value") or {}
if h:
    t = [f"Диск {h['disk_avail_gb']} ГБ вільно ({h['disk_used_pct']}%), "
         f"памʼять {h['ram_avail_mb']/1024:.1f} ГБ, {h['temp_c']}°C, аптайм {h['uptime_days']} дн"]
    s = [f"Диск: вільно {u.num(h['disk_avail_gb'])} {u.plural(h['disk_avail_gb'],'гігабайт','гігабайти','гігабайт')}, "
         f"зайнято {u.percent(h['disk_used_pct'])}.",
         f"Памʼять: {u.num(round(h['ram_avail_mb']/1024))} гігабайт вільно з {u.gen(round(h['ram_total_mb']/1024))}.",
         f"Температура {u.degrees(h['temp_c'])}."]
    if sv:
        ok = sv.get("tmux") and sv.get("claude_home") and sv.get("memory_timer") and not sv.get("exited")
        t.append("Сервіси: усе працює" if ok else "⚠️ " + probes["services"]["text"])
        s.append("Усі сервіси працюють." if ok else probes["services"]["text"] + ".")
    section("Сервер", t, s)

# — новини —
nt, ns = [], []
for tid in topics:
    p = probes.get(f"news:{tid}", {})
    items = (p.get("value") or {}).get("items") or []
    meta = json.loads((HOME / "status" / "topics" / f"{tid}.json").read_text(encoding="utf-8"))
    name = meta.get("назва", tid)
    if not items:
        continue
    def clean(x):
        x = re.split(r" - [A-ZА-ЯЇІЄ][^-]*$", x)[0]
        return x.replace("#", "номер ").strip()
    nt.append(f"_{name}_: " + "; ".join(clean(i["title"]) for i in items[:3]))
    ns.append(f"{name}. " + " ".join(clean(i["title"]).rstrip(".") + "." for i in items[:3]))
if nt:
    section("Новини", nt, ns)
else:
    section("Новини", ["Нічого нового за темами."], ["За темами нічого нового."])

text_msg = "\n".join(text)
speech_msg = " ".join(speech)

if "--показати" in sys.argv:
    print(text_msg); print("\n--- для озвучки ---\n"); print(speech_msg)
else:
    subprocess.run([str(HOME / "notify.sh"), text_msg])
    mp3, ogg = "/tmp/noos-digest.mp3", "/tmp/noos-digest.ogg"
    subprocess.run([str(HOME / "voice" / "el_say.sh"), mp3, speech_msg],
                   stdout=subprocess.DEVNULL)
    subprocess.run([str(HOME / ".venv-voice" / "bin" / "python"),
                    str(HOME / "voice" / "to_ogg.py"), mp3, ogg], stdout=subprocess.DEVNULL)
    env = dict(l.strip().split("=", 1) for l in (HOME / ".env.telegram").read_text().splitlines() if "=" in l)
    subprocess.run(["curl", "-sS", "-m", "60", "-X", "POST",
                    f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendVoice",
                    "-F", f"chat_id={env['TELEGRAM_CHAT_ID']}", "-F", f"voice=@{ogg}",
                    "-o", "/dev/null"])
    print("надіслано")
