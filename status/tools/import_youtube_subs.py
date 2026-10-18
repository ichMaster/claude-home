#!/usr/bin/env python
"""Import YouTube subscriptions from a Google Takeout CSV into config.local.json.

Takeout: takeout.google.com -> YouTube and YouTube Music -> subscriptions ->
`subscriptions.csv` (the header is localized, so both English and Ukrainian column
names are accepted).

  status/tools/import_youtube_subs.py ~/Downloads/subscriptions.csv [--limit 40]

Channels are written to config.local.json (git-ignored) under probes.youtube.channels,
so the public config keeps no record of what the user watches.
"""
import csv, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import ROOT

src = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
if not src or not src.exists():
    sys.exit(__doc__)
limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0

rows = list(csv.DictReader(src.read_text(encoding="utf-8-sig").splitlines()))

def pick(row, *names):
    """Takeout localizes the CSV header, so accept both English and Ukrainian."""
    for n in names:
        for key in row:
            if key.strip().lower() == n.lower():
                return (row[key] or "").strip()
    return ""

channels = []
for r in rows:
    cid = pick(r, "Channel Id", "Channel ID", "Ідентифікатор каналу")
    name = pick(r, "Channel Title", "Channel title", "Назва каналу")
    if cid.startswith("UC") and name:
        channels.append({"name": name, "id": cid})
if limit:
    channels = channels[:limit]

local = ROOT / "config.local.json"
data = json.loads(local.read_text(encoding="utf-8")) if local.exists() else {}
data.setdefault("probes", {}).setdefault("youtube", {})["channels"] = channels
local.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"записано {len(channels)} каналів у {local}")
