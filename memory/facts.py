#!/usr/bin/env python
"""Факти, які треба пам'ятати між сесіями.

  memory/facts.py add "текст" [--pin 1|2|0] [--tag ім'я ...]
  memory/facts.py list [--all]
  memory/facts.py prompt          # блок для системної підказки
  memory/facts.py rm <id>
  memory/facts.py pin <id> <0|1|2>

Кожен факт — окремий файл у memory/facts/. Рівень важливості:
  1 — критичне, завжди в підказці
  2 — важливе, потрапляє якщо лишилось місце
  0 — лише в пошуку
"""
import sys, re, json, datetime
from pathlib import Path

DIR = Path.home() / "claude-home" / "memory" / "facts"
MAX_FACTS = 100        # скільки взагалі тримаємо
MAX_IN_PROMPT = 25     # скільки потрапляє в підказку
MAX_LEN = 240          # обрізання факту в підказці, ~3 рядки

def slug(text):
    s = re.sub(r"[^\w\s-]", "", text.lower())[:40]
    return re.sub(r"\s+", "-", s.strip()) or "fact"

def load():
    out = []
    for f in sorted(DIR.glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        meta, _, body = raw.partition("\n---\n")
        head = {}
        for line in meta.strip().strip("-").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                head[k.strip()] = v.strip()
        out.append({"file": f, "id": f.stem, "pin": int(head.get("pin", 0)),
                    "tags": head.get("tags", ""), "added": head.get("added", ""),
                    "text": body.strip()})
    return out

def add(text, pin, tags):
    DIR.mkdir(parents=True, exist_ok=True)
    facts = load()
    if len(facts) >= MAX_FACTS:
        print(f"у сховищі вже {len(facts)} фактів (ліміт {MAX_FACTS}) — "
              f"прибери застаріле через rm", file=sys.stderr)
    base = slug(text); name = base; i = 2
    while (DIR / f"{name}.md").exists():
        name = f"{base}-{i}"; i += 1
    today = datetime.date.today().isoformat()
    (DIR / f"{name}.md").write_text(
        f"---\npin: {pin}\ntags: {','.join(tags)}\nadded: {today}\n---\n{text.strip()}\n",
        encoding="utf-8")
    print(name)

def prompt():
    facts = sorted([f for f in load() if f["pin"] > 0],
                   key=lambda f: (f["pin"], f["added"]))[:MAX_IN_PROMPT]
    if not facts:
        return ""
    lines = ["## Факти, які треба пам'ятати", ""]
    for f in facts:
        t = " ".join(f["text"].split())
        if len(t) > MAX_LEN:
            t = t[:MAX_LEN - 1].rstrip() + "…"
        lines.append(f"- {t}")
    lines += ["", f"(решта фактів і весь архів розмов — через ./memory/search.sh)"]
    return "\n".join(lines)

cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
if cmd == "add":
    args = sys.argv[2:]
    pin, tags, text = 1, [], []
    i = 0
    while i < len(args):
        if args[i] == "--pin": pin = int(args[i + 1]); i += 2
        elif args[i] == "--tag": tags.append(args[i + 1]); i += 2
        else: text.append(args[i]); i += 1
    add(" ".join(text), pin, tags)
elif cmd == "prompt":
    print(prompt())
elif cmd == "rm":
    p = DIR / f"{sys.argv[2]}.md"
    p.unlink(); print(f"видалено {sys.argv[2]}")
elif cmd == "pin":
    p = DIR / f"{sys.argv[2]}.md"
    s = p.read_text(encoding="utf-8")
    p.write_text(re.sub(r"^pin: \d+", f"pin: {sys.argv[3]}", s, count=1, flags=re.M), encoding="utf-8")
    print(f"{sys.argv[2]} → pin {sys.argv[3]}")
else:
    facts = load()
    show_all = "--all" in sys.argv
    for f in sorted(facts, key=lambda f: (f["pin"] == 0, f["pin"], f["id"])):
        if f["pin"] == 0 and not show_all:
            continue
        t = " ".join(f["text"].split())
        print(f"[pin {f['pin']}] {f['id']:34} {t[:90]}")
    print(f"\nвсього {len(facts)} з {MAX_FACTS}; у підказку йде до {MAX_IN_PROMPT}")
