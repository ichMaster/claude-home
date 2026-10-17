#!/usr/bin/env python3
"""PostToolUse-хук: пише в changelog/YYYY-MM-DD.jsonl лише ті виклики, що щось змінюють.

Читає JSON хука зі stdin: {session_id, cwd, tool_name, tool_input, tool_response}.
Читання (cat, grep, ls, sed -n…) не логується — журнал про зміни, не про перегляди.
Хук мусить бути безшумним: будь-яка помилка гаситься, exit 0.
"""
import json, os, re, sys
from datetime import datetime

LOG_DIR = os.path.expanduser("~/claude-home/changelog")
MAX_DETAIL = 400

# команди, що залишають слід у системі
MUTATING = re.compile(
    r"(^|[;&|]\s*)(rm|rmdir|mv|cp|mkdir|touch|ln|chmod|chown|truncate|dd|tee|install|patch"
    r"|systemctl|loginctl|crontab|timedatectl|apt|apt-get|dpkg|snap|pip|pip3|npm|pnpm|yarn|cargo|go"
    r"|git|sqlite3|psql|mysql|docker|podman|tmux|kill|pkill|killall|virtualenv|curl|wget)\b"
    r"|\bsed\s+(-[a-zA-Z]*i|--in-place)"
    r"|>>?\s*[^&\s]"
    r"|\bpython\S*\s.*\b(ingest|facts|write|add|rm)\b"
)
# явно нешкідливе, навіть якщо збіглося вище
READONLY = re.compile(
    r"^\s*(cat|less|head|tail|ls|stat|wc|grep|rg|find|file|df|du|ps|free|uptime|date|which|whoami|env|pwd)\b"
    r"|^\s*git\s+(status|log|diff|show|branch|remote|rev-parse)\b"
    r"|^\s*systemctl\s+(--user\s+)?(status|list-timers|list-units|show|cat|is-active|is-enabled)\b"
    r"|^\s*(pip|pip3|npm)\s+(list|show|freeze)\b"
    r"|^\s*sed\s+-n\b"
)


def classify(payload):
    """-> (kind, target, detail) або None, якщо подію не логуємо."""
    tool = payload.get("tool_name") or ""
    inp = payload.get("tool_input") or {}
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or "?"
        if tool == "Write":
            detail = f"{len((inp.get('content') or '').splitlines())} рядків"
        else:
            detail = (inp.get("old_string") or "")[:80].replace("\n", " ⏎ ")
        return tool.lower(), path, detail
    if tool == "Bash":
        cmd = (inp.get("command") or "").strip()
        if not cmd:
            return None
        m = MUTATING.search(cmd)
        if READONLY.search(cmd) or not m:
            return None
        # ярлик події — саме та дія, через яку команда вважається змінною,
        # а не перший токен (бо він часто `cd` перед heredoc)
        verb = next((g for g in m.groups()[1:] if g), None) or m.group(0).strip()
        verb = verb.strip(" ;&|")
        if verb.startswith(">"):
            redir = re.search(r">>?\s*([^&\s]\S*)", cmd)
            verb = "запис → " + redir.group(1) if redir else "запис у файл"
        detail = " ⏎ ".join(x.strip() for x in cmd.splitlines() if x.strip())
        return "bash", verb, detail[:MAX_DETAIL]
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    try:
        res = classify(payload)
        if not res:
            return
        kind, target, detail = res
        home = os.path.expanduser("~")
        if target.startswith(home):
            target = "~" + target[len(home):]
        rec = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "kind": kind,
            "target": target,
            "detail": detail,
            "session": (payload.get("session_id") or "")[:8],
            "cwd": payload.get("cwd") or "",
        }
        os.makedirs(LOG_DIR, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(LOG_DIR, f"{day}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
