#!/usr/bin/env python
"""Probe: what is new in Gmail since the previous check.

Works over IMAP, reads headers only and marks nothing as read (BODY.PEEK).
Keys live in `~/claude-home/.env.gmail`:
    GMAIL_USER=your-address@gmail.com
    GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx   # an app password, not the account password

State (the last seen UID) is `status/state/mail.json`, so "new" means "was not there
at the previous check" rather than "unread".
"""
import email, imaplib, json, os, re, sys
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path

HOME = path("paths.home")
STATE = HOME / "status" / "state" / "mail.json"
ENV = HOME / ".env.gmail"
RULES = HOME / "status" / "mail-rules.json"
LOOKBACK_DAYS = conf("probes.mail.lookback_days", 2)  # window used when no state yet

DEFAULT_RULES = {
    "шум": ["newsletters-noreply@linkedin.com", "udemymail.com", "aliexpress.com",
            "alibaba.com", "chess.com", "noreply@youtube.com", "facebookmail.com",
            "info@meetup.com", "news@", "newsletter@", "digest@", "promo"],
    "важливе": ["security", "безпека", "рахунок", "invoice", "payment", "платіж",
                "квиток", "ticket", "школа", "school", "банк", "bank", "податк",
                "термін", "deadline", "verification", "код підтвердження"],
}


def env():
    cfg = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def hdr(raw):
    try:
        return str(make_header(decode_header(raw or "")))
    except Exception:
        return raw or ""


def out(**kw):
    kw.setdefault("id", "mail")
    kw.setdefault("ttl", 600)
    print(json.dumps(kw, ensure_ascii=False))
    sys.exit(0)


cfg = env()
user, pw = cfg.get("GMAIL_USER"), cfg.get("GMAIL_APP_PASSWORD")
if not user or not pw:
    out(ok=False, severity="warn", ttl=3600,
        text="Пошта: немає ключів. Поклади GMAIL_USER і GMAIL_APP_PASSWORD "
             "у ~/claude-home/.env.gmail (пароль застосунку Google)")

rules = DEFAULT_RULES
if RULES.exists():
    try:
        rules = {**DEFAULT_RULES, **json.loads(RULES.read_text(encoding="utf-8"))}
    except Exception:
        pass

state = json.loads(STATE.read_text()) if STATE.exists() else {}
last_uid = int(state.get("last_uid", 0))

try:
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(user, pw)
    M.select("INBOX", readonly=True)

    if last_uid:
        typ, data = M.uid("search", None, f"UID {last_uid + 1}:*")
    else:
        since = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        typ, data = M.uid("search", None, f"(SINCE {since})")
    uids = [u for u in (data[0].split() if data and data[0] else [])
            if int(u) > last_uid]

    items = []
    for uid in uids[-60:]:                     # більше за раз не читаємо
        typ, d = M.uid("fetch", uid,
                       "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK" or not d or not isinstance(d[0], tuple):
            continue
        msg = email.message_from_bytes(d[0][1])
        frm, subj = hdr(msg.get("From")), hdr(msg.get("Subject"))
        addr = (re.search(r"[\w.+-]+@[\w.-]+", frm) or [""])[0] if "@" in frm else ""
        blob = f"{frm} {subj}".lower()
        noise = any(s.lower() in blob for s in rules["шум"])
        important = any(s.lower() in blob for s in rules["важливе"])
        items.append({"uid": int(uid), "from": frm[:80], "addr": addr,
                      "subject": subj[:120],
                      "kind": "важливе" if important else ("шум" if noise else "звичайне")})
    M.logout()

    if uids:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"last_uid": max(int(u) for u in uids),
                                     "checked": datetime.now().isoformat(timespec="seconds")},
                                    ensure_ascii=False, indent=1))

    imp = [i for i in items if i["kind"] == "важливе"]
    ord_ = [i for i in items if i["kind"] == "звичайне"]
    noise_n = len(items) - len(imp) - len(ord_)

    if not items:
        out(ok=True, severity="quiet", value={"total": 0},
            text="Пошта: нічого нового")

    lines = [f"Пошта: {len(items)} нових — важливих {len(imp)}, "
             f"звичайних {len(ord_)}, шуму {noise_n}"]
    for i in (imp + ord_)[:6]:
        who = i["addr"] or i["from"]
        lines.append(f"  • {who}: {i['subject']}")
    if len(imp) + len(ord_) > 6:
        lines.append(f"  … і ще {len(imp) + len(ord_) - 6}")

    out(ok=True, severity="warn" if imp else "info",
        value={"total": len(items), "important": len(imp),
               "ordinary": len(ord_), "noise": noise_n, "items": items[:20]},
        text="\n".join(lines))

except imaplib.IMAP4.error as e:
    out(ok=False, severity="warn", ttl=1800,
        text=f"Пошта: IMAP відмовив ({e}). Перевір пароль застосунку й що IMAP увімкнений")
except Exception as e:
    out(ok=False, severity="warn", text=f"Пошта недоступна: {e}")
