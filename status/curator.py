#!/usr/bin/env python
"""News editor: ranks candidates, picks what matters and retells the substance.

  curator.py [topic ...]       — collect, select, save to cache/curated.json
  curator.py --show        — print without saving

Candidates come from the Guardian (with full article text) and Google News
(headlines); one model call then ranks them and writes the summary in Ukrainian.
"""
import json, os, subprocess, sys
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

HOME = path("paths.home")
TOPICS = HOME / "status" / "topics"
PY_BIN = str(HOME / ".venv-voice" / "bin" / "python")

env = {}
for f in (".env.ai", ".env.news"):
    p = HOME / f
    if p.exists():
        env.update(dict(l.strip().split("=", 1) for l in p.read_text().splitlines() if "=" in l))

MODEL = env.get("CURATOR_MODEL", "claude-opus-5")

class Item(BaseModel):
    тема: str = Field(description="id теми, з якої взята новина")
    заголовок: str = Field(description="стислий заголовок українською, без назви видання")
    суть: str = Field(description="3-5 речень: що сталося, чому це важливо, що з цього випливає")
    джерело: str
    посилання: str
    вага: int = Field(description="1-5, наскільки це варте уваги читача")

class Digest(BaseModel):
    новини: List[Item]

def candidates(tid):
    t = json.loads((TOPICS / f"{tid}.json").read_text(encoding="utf-8"))
    out = []
    g = t.get("guardian")
    if g:
        raw = subprocess.run([PY_BIN, str(HOME / "status" / "sources" / "guardian.py"),
                              g.get("запит", t["запит"]), g.get("розділ", "-"), "10"],
                             capture_output=True, text=True).stdout
        if raw.strip():
            out += json.loads(raw)
    raw = subprocess.run([PY_BIN, str(HOME / "status" / "probes" / "news.py"), tid],
                         capture_output=True, text=True).stdout
    if raw.strip():
        d = json.loads(raw)
        for i in (d.get("value") or {}).get("items", []):
            out.append({"source": i["source"], "title": i["title"], "url": i["link"],
                        "lead": "", "body": ""})
    return t, out

topics = [a for a in sys.argv[1:] if not a.startswith("--")] or \
         sorted(p.stem for p in TOPICS.glob("*.json"))

pool = {}
for tid in topics:
    meta, items = candidates(tid)
    if items:
        pool[tid] = {"назва": meta["назва"], "опис": meta.get("опис", ""), "кандидати": items}

if not pool:
    print("кандидатів немає"); sys.exit(0)

brief = []
for tid, d in pool.items():
    brief.append(f"\n## Тема {tid} — {d['назва']}\n{d['опис']}\n")
    for n, c in enumerate(d["кандидати"], 1):
        brief.append(f"[{tid}#{n}] {c['title']} ({c['source']}) {c['url']}\n"
                     f"{c.get('lead','')}\n{(c.get('body') or '')[:2500]}\n")

USER_NAME = os.environ.get("NOOS_USER_NAME", "користувача")
USER_CITY = os.environ.get("NOOS_USER_CITY", "його міста")
SYSTEM = f"""Ти редактор щоденного дайджесту для однієї людини — {USER_NAME} з {USER_CITY}.
Він інженер: цікавиться штучним інтелектом, embedded-розробкою, робототехнікою,
фізикою й космосом, а також тим, що відбувається в Україні та світі.

Твоя робота — не переказувати заголовки, а відібрати те, що справді варте уваги,
і пояснити суть.

Правила:
- З кожної теми бери щонайбільше 2-3 новини. Якщо в темі немає нічого вартого — не бери нічого.
- Відкидай прес-релізи, рубрики, рекламу, дублікати одного сюжету.
- «Суть» — 3-5 речень живою українською: що сталося, деталі з тексту статті,
  чому це важливо. Не починай з «У статті йдеться».
- Якщо тексту статті немає, а є лише заголовок — пиши стисліше й не вигадуй деталей.
- Вага: 5 — те, що змінює картину світу або прямо стосується його роботи; 1 — цікавинка.
- Жодної латиниці в переказі, крім власних назв."""

client = anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY"))
resp = client.messages.parse(
    model=MODEL,
    max_tokens=16000,
    system=SYSTEM,
    messages=[{"role": "user", "content": "Ось кандидати на сьогодні:\n" + "\n".join(brief)}],
    output_format=Digest,
)
digest = resp.parsed_output
items = sorted(digest.новини, key=lambda i: -i.вага)

if "--show" in sys.argv:
    for i in items:
        print(f"\n[{i.вага}] {i.тема} — {i.заголовок} ({i.джерело})\n{i.суть}")
    u = resp.usage
    print(f"\nвхід {u.input_tokens}, вихід {u.output_tokens} токенів")
else:
    (HOME / "status" / "cache" / "curated.json").write_text(
        json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"відібрано {len(items)} новин, модель {MODEL}, "
          f"вхід {resp.usage.input_tokens} / вихід {resp.usage.output_tokens} токенів")
