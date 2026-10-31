#!/usr/bin/env python
"""Two-way traffic for the named bots: read what the owner writes to Zirka and Bruno,
answer in their own voice.

The main bot is the conversation and the session polls it directly; these two only
broadcast, so nothing was reading their queues at all — a reply sent to the horoscope chat
simply expired after a day (the owner, 2026-10-30: «я і неї буду писати відповіді»). This
script closes the loop: `getUpdates` on each bot's own token (a separate queue, so no
conflict with the session's polling), Deepgram for voice messages, one headless call for
the answer, and `notify.sh --bot` to send it back in that bot's voice.

Hard limits, and they are the point rather than a detail:

* **Only the owner is answered.** The bots are public — anyone who guesses the username can
  write to them — so every update from another chat is dropped and logged, never answered.
  Without this a stranger holds a conversation with the model on his quota.
* **The answering call has no tools.** `--allowedTools ""` plus no MCP: the reply is text and
  nothing else, so a message in the chat cannot make anything happen. Incoming text is data,
  not instruction, and the prompts say so.
* **A rate cap per bot per hour** (`telegram.inbox.max_per_hour`), so a loop or a flood
  cannot burn the quota.
* **Feedback is recorded here, not by the model.** A remark about the day sent to Zirka goes
  into `mood_feedback.py add` from this script, deterministically — the model never runs a
  command.

    inbox.py                 poll every bot once
    inbox.py --bot zirka     one bot only
    inbox.py --dry-run       show what would be answered, send nothing
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf, path                                          # noqa: E402

HOME = Path(__file__).resolve().parents[2]
PROMPTS = HOME / "status" / "bots"
STATE = HOME / "status" / "state" / "bots"
API = "https://api.telegram.org"

# bot name → (kind in telegram.bots, voice role, prompt file)
BOTS = {
    "zirka": ("mood", "mood", "zirka.md"),
    "bruno": ("news", "news", "bruno.md"),
}

# Mimes that cannot be text, so the file is refused before it is downloaded. Everything
# else — including the application/octet-stream Telegram gives a long paste — is fetched
# and judged on its bytes by `as_text()` (t1054).
BINARY_MIME_PREFIXES = ("image/", "audio/", "video/", "font/")
BINARY_MIMES = {"application/pdf", "application/zip", "application/gzip",
                "application/x-tar", "application/x-7z-compressed",
                "application/octet-stream+binary", "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def as_text(blob: bytes) -> str:
    """The file's text, or "" when it is not text after all.

    A NUL byte means binary, always. Otherwise strict UTF-8 first; a lenient decode is
    accepted only when the replacement characters are a small fraction, so a mis-labelled
    text file still reads while binary never reaches the model as mojibake.
    """
    if b"\x00" in blob:
        return ""
    try:
        return blob.decode("utf-8").strip()
    except UnicodeDecodeError:
        text = blob.decode("utf-8", "replace")
        return text.strip() if text.count("�") <= max(2, len(text) // 100) else ""


def env_telegram() -> dict[str, str]:
    """Read `.env.telegram` as plain KEY=VALUE. Not sourced through a shell on purpose: a
    malformed line should be skipped here, not break the whole run (2026-10-30, a line with
    literal angle brackets took the channel down)."""
    out: dict[str, str] = {}
    f = Path(str(conf("telegram.env", "~/claude-home/.env.telegram"))).expanduser()
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            out[key] = value
    return out


def api(token: str, method: str, **params) -> dict:
    url = f"{API}/bot{token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def state_file(bot: str) -> Path:
    STATE.mkdir(parents=True, exist_ok=True)
    return STATE / f"{bot}.json"


def load_state(bot: str) -> dict:
    f = state_file(bot)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"offset": 0, "history": [], "answers": []}


def save_state(bot: str, st: dict) -> None:
    st["history"] = st.get("history", [])[-int(conf("telegram.inbox.history", 12)):]
    state_file(bot).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def message_shape(msg: dict) -> dict:
    """What kind of message this was — the keys it carried, and a document's metadata.

    «без тексту» on its own says nothing: a photo, a voice note that transcribed to
    silence and a document with an unexpected mime all look the same in the log, and
    telling them apart cost a round trip through the owner (t1054). Metadata only — the
    content is not copied here.
    """
    skip = {"chat", "from", "date", "message_id", "entities", "caption_entities"}
    shape = {"keys": sorted(k for k in msg if k not in skip)}
    doc = msg.get("document") or {}
    if doc:
        shape["document"] = {"mime": doc.get("mime_type") or "",
                             "name": doc.get("file_name") or "",
                             "size": doc.get("file_size")}
    return shape


def log_dropped(bot: str, why: str, update: dict) -> None:
    """Anything not answered is written down — a stranger writing to a public bot is worth
    knowing about, and a silent drop looks like a bug."""
    f = STATE / "dropped.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    msg = update.get("message") or update.get("edited_message") or {}
    rec = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "bot": bot, "why": why,
           "chat": msg.get("chat", {}).get("id"),
           "from": msg.get("from", {}).get("id"),
           "shape": message_shape(msg),
           "text": (msg.get("text") or "")[:200]}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def transcribe(token: str, file_id: str) -> str:
    """Voice message → text through the existing Deepgram script. He speaks rather than
    types, so a voice-only path would lose most of what he says."""
    info = api(token, "getFile", file_id=file_id)
    if not info.get("ok"):
        return ""
    remote = info["result"]["file_path"]
    tmp = Path(f"/tmp/noos-inbox-{file_id[:16]}.oga")
    with urllib.request.urlopen(f"{API}/file/bot{token}/{remote}", timeout=60) as r:
        tmp.write_bytes(r.read())
    try:
        out = subprocess.run([str(HOME / "voice" / "dg_stt.sh"), str(tmp), "uk"],
                             capture_output=True, text=True, timeout=180, cwd=str(HOME))
        return out.stdout.strip()
    finally:
        tmp.unlink(missing_ok=True)


def read_document(token: str, doc: dict) -> str:
    """A large paste arrives as a .txt document, not as message text — Telegram's client turns
    a long paste into a file (the owner, 2026-10-31: Zirka could not take the reference, «може
    тому що меседж дуже великий»). Download it and read it as the message, if it is text and
    not too big to hold in memory."""
    mime = (doc.get("mime_type") or "").lower()
    size = int(doc.get("file_size") or 0)
    if size > int(conf("telegram.inbox.max_document_bytes", 262144)):
        return ""
    # Judge by the bytes, not by the label. Telegram picks the mime itself and gives a long
    # paste something like application/octet-stream with no extension; the old whitelist
    # (text/* or .txt/.md/.csv/.log) refused exactly those, so a forwarded reference was
    # dropped as «без тексту» (t1054). Only mimes that are certainly binary are refused
    # here — everything else is fetched and decided on content.
    if mime.startswith(BINARY_MIME_PREFIXES) or mime in BINARY_MIMES:
        return ""
    info = api(token, "getFile", file_id=doc["file_id"])
    if not info.get("ok"):
        return ""
    remote = info["result"]["file_path"]
    try:
        with urllib.request.urlopen(f"{API}/file/bot{token}/{remote}", timeout=60) as r:
            return as_text(r.read())
    except Exception:                                 # noqa: BLE001
        return ""


def zirka_context() -> dict[str, str]:
    f = Path(str(path("astro.state", "status/state/mood.json")))
    if not f.exists():
        return {"ПРОГНОЗ": "(сьогоднішнього читання немає)", "БІОРИТМИ": "(немає)"}
    d = json.loads(f.read_text(encoding="utf-8"))
    return {"ПРОГНОЗ": f"({d.get('day', '')})\n{d.get('summary', '') or '(немає)'}",
            "БІОРИТМИ": f"{d.get('biorhythms', '')}\n{d.get('bio_conclusion', '')}".strip()
                        or "(немає)"}


def bruno_context() -> dict[str, str]:
    news = "(нічого не надсилалось)"
    f = Path(str(path("digest.news_state", "status/state/news.json")))
    if f.exists():
        try:
            sent = json.loads(f.read_text(encoding="utf-8")).get("sent", [])
            cutoff = (datetime.now() - timedelta(days=2)).date().isoformat()
            recent = [s for s in sent if str(s.get("day", s.get("ts", "")))[:10] >= cutoff]
            rows = recent[-10:] or sent[-6:]
            news = "\n".join(f"- {s.get('title', '')} — {s.get('url', '')}" for s in rows)
        except (json.JSONDecodeError, AttributeError):
            pass
    video = "(добірки немає)"
    f = HOME / "status" / "state" / "youtube-last-digest.json"
    if f.exists():
        try:
            items = json.loads(f.read_text(encoding="utf-8")).get("items", [])[:40]
            video = "\n".join(f"- {i.get('channel', '')}: {i.get('title', '')} — "
                              f"{i.get('link', '')}" for i in items) or video
        except json.JSONDecodeError:
            pass
    return {"НОВИНИ": news, "ВІДЕО": video}


def intent(message: str, prev_scope: str = "") -> dict:
    """What Bruno is being asked for: a chat turn or a topic search. One cheap call with no
    tools; anything unparseable falls back to chat, because answering as chat is always safe
    while searching for a mis-parsed query is noise.

    `prev_scope` is the area of the previous search. A follow-up that only rephrases the query
    ("спробуй так …", "давай ще раз але …") without naming an area should keep the previous
    one — otherwise "search YouTube for X" followed by "try Y instead" silently falls back to
    both and answers with news (the owner, 2026-10-31: Bruno searched news for a YouTube-only
    request)."""
    prompt = (PROMPTS / "intent.md").read_text(encoding="utf-8").replace(
        "{{ПОВІДОМЛЕННЯ}}", message).replace(
        "{{ПОПЕРЕДНЯ_ОБЛАСТЬ}}", prev_scope or "немає")
    try:
        raw = call_claude(prompt, conf("telegram.inbox.intent_model", "sonnet"), 90)
    except Exception as e:                                               # noqa: BLE001
        print(f"намір не визначився: {e}")
        return {"mode": "chat"}
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"mode": "chat"}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"mode": "chat"}
    if d.get("mode") != "search" or not str(d.get("query", "")).strip():
        return {"mode": "chat"}
    scope = d.get("scope") if d.get("scope") in ("news", "youtube", "both") else "both"
    # a bare "try this instead" keeps the previous area rather than widening to both
    if d.get("keep_scope") and prev_scope in ("news", "youtube", "both"):
        scope = prev_scope
    return {"mode": "search", "scope": scope, "query": str(d["query"]).strip()}


def zirka_kind(message: str) -> dict:
    """What arrived in the horoscope chat: another astrologer's reading to learn from, a
    remark about how the day really went, or ordinary talk. Misreading a reading as feedback
    would poison the calibration, so this is classified rather than guessed from length."""
    prompt = (PROMPTS / "zirka_intent.md").read_text(encoding="utf-8").replace(
        "{{ПОВІДОМЛЕННЯ}}", message)
    try:
        raw = call_claude(prompt, str(conf("telegram.inbox.intent_model", "sonnet")), 120)
    except Exception as e:                                               # noqa: BLE001
        print(f"тип повідомлення не визначився: {e}")
        return {"kind": "feedback"}
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"kind": "feedback"}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"kind": "feedback"}
    if d.get("kind") not in ("reference", "feedback", "chat"):
        d["kind"] = "feedback"
    return d


def take_reference(message: str, meta: dict) -> str:
    """Store another astrologer's reading and distil rules out of it right away, so the next
    morning already reads differently (the owner, 2026-10-30). Returns what was learned, for
    the reply."""
    day = datetime.now().date() + timedelta(days=1 if meta.get("day") == "tomorrow" else 0)
    text = (meta.get("clean") or message).strip()
    cmd = [str(HOME / ".venv-voice" / "bin" / "python"), str(HOME / "status" / "astro_learn.py"),
           "add", text, "--day", day.isoformat(), "--period", meta.get("period") or "день",
           "--learn"]
    if meta.get("author"):
        cmd += ["--author", str(meta["author"])]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(HOME))
    if out.returncode != 0:
        return f"(записати не вдалось: {out.stderr.strip()[:200]})"
    return out.stdout.strip()


def run_search(scope: str, query: str) -> str:
    """Run the search here, not in the model: the answering call has no tools on purpose."""
    out = subprocess.run([str(HOME / ".venv-voice" / "bin" / "python"),
                          str(PROMPTS / "search.py"), scope, query],
                         capture_output=True, text=True, timeout=120, cwd=str(HOME))
    if out.returncode != 0:
        return f"(пошук не вдався: {out.stderr.strip()[:200]})"
    try:
        d = json.loads(out.stdout)
    except json.JSONDecodeError:
        return "(пошук повернув не те, що очікувалось)"
    lines = [f"Запит: {d.get('query', query)}"]
    if "news" in d:
        lines.append("\nНовини:" if d["news"] else "\nНовини: нічого не знайшлось")
        for n in d["news"]:
            lines.append(f"- [{n.get('source', '')}] {n.get('title', '')} — {n.get('link', '')}")
            if n.get("snippet"):
                lines.append(f"  анотація: {n['snippet']}")
            # the body is what the two or three sentences of substance are written from;
            # absent means paywalled or blocked, and the snippet is all there is
            lines.append(f"  текст: {n['text']}" if n.get("text")
                         else "  текст: (не дістався — лише анотація)")
    if "videos" in d:
        lines.append("\nВідео з підписок:" if d["videos"]
                     else "\nВідео з підписок: нічого не знайшлось")
        for v in d["videos"]:
            lines.append(f"- {v.get('channel', '')}: {v.get('title', '')} — {v.get('link', '')}")
        lines.append(f"\nАрхів підписок покриває: {d.get('archive', 'невідомо')}")
    return "\n".join(lines)


def build_prompt(bot: str, history: list[dict], message: str,
                 search: str = "") -> str:
    _, _, prompt_file = BOTS[bot]
    text = (PROMPTS / "common.md").read_text(encoding="utf-8") + "\n\n"
    body = (PROMPTS / prompt_file).read_text(encoding="utf-8")
    context = zirka_context() if bot == "zirka" else bruno_context()
    context["ПОШУК"] = search or "(пошуку не було)"
    context["НАВЧАННЯ"] = search if bot == "zirka" and search else "(не було)"
    for key, value in context.items():
        body = body.replace("{{" + key + "}}", value)
    text += body + "\n\n## Останні репліки в цьому чаті\n\n"
    text += ("\n".join(f"{'він' if h['role'] == 'user' else 'ти'}: {h['text']}"
                       for h in history[-8:]) or "(порожньо)")
    text += ("\n\n## Нове повідомлення\n\n" + message +
             "\n\nВідповідай текстом, без заголовків і без розмітки. Нічого, крім самої "
             "відповіді, не виводь.")
    return text


def call_claude(prompt: str, model: str = "", timeout: int = 180) -> str:
    """One headless call with no tools and no MCP: the reply is text, so nothing said in a
    bot's chat can make anything happen."""
    cmd = ["claude", "-p", prompt,
           "--settings", str(HOME / "status" / "digest-settings.json"),
           "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
           "--allowedTools", ""]
    if model:
        cmd += ["--model", model]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         cwd=str(HOME), stdin=subprocess.DEVNULL)
    if out.returncode != 0:
        raise RuntimeError(f"виклик не вдався (код {out.returncode}): {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def answer(bot: str, history: list[dict], message: str, search: str = "") -> str:
    return re.sub(r"\*+", "",
                  call_claude(build_prompt(bot, history, message, search),
                              str(conf("telegram.inbox.model", "")),
                              int(conf("telegram.inbox.timeout", 180))))


HANDOFF = re.compile(r"^\s*ПЕРЕДАТИ\s*:\s*(.+)$", re.M)


def split_handoff(reply: str) -> tuple[str, str]:
    """Pull the `ПЕРЕДАТИ:` line out of a reply. The bot says "це через головний чат" in its
    own chat; the line itself never goes there (the owner, 2026-10-30: «хай так пишуть, а ти
    сам в цей чат пиши як це можна зробити»)."""
    m = HANDOFF.search(reply or "")
    if not m:
        return reply, ""
    return HANDOFF.sub("", reply).strip(), m.group(1).strip()


def hand_over(bot: str, asked: str, reply: str, request: str) -> None:
    """Tell the main chat what was wanted and how to actually do it. One extra call, in the
    main voice, because the answer belongs where the actions happen."""
    prompt = ((PROMPTS / "handoff.md").read_text(encoding="utf-8")
              .replace("{{БОТ}}", bot).replace("{{ЗАПИТ}}", f"{asked}\n\n({request})")
              .replace("{{ВІДПОВІДЬ}}", reply or "(нічого)"))
    try:
        text = re.sub(r"\*+", "", call_claude(prompt, str(conf("telegram.inbox.model", "")),
                                              int(conf("telegram.inbox.timeout", 180))))
    except Exception as e:                                               # noqa: BLE001
        text = (f"У чаті {bot} просили: {request}. Там цього зробити не можна — "
                f"скажи мені тут, зроблю. (підказку згенерувати не вдалось: {e})")
    if not text:
        return
    name = {"zirka": "Зірка", "bruno": "Бруно"}.get(bot, bot)
    subprocess.run([str(HOME / "notify.sh"), f"{name} не змогла відповісти.\n\n{text}"
                    if bot == "zirka" else f"{name} не змiг відповісти.\n\n{text}"],
                   check=False, cwd=str(HOME), timeout=300)


def within_cap(st: dict, bot: str) -> bool:
    cap = int(conf("telegram.inbox.max_per_hour", 20))
    hour_ago = (datetime.now().astimezone() - timedelta(hours=1)).isoformat()
    recent = [t for t in st.get("answers", []) if t >= hour_ago]
    st["answers"] = recent[-200:]
    return len(recent) < cap


def record_feedback(text: str) -> None:
    """A remark sent to Zirka is calibration data. Done here rather than by the model: the
    answering call has no tools on purpose."""
    if len(text) < int(conf("telegram.inbox.feedback_min_chars", 25)):
        return
    subprocess.run([str(HOME / ".venv-voice" / "bin" / "python"),
                    str(HOME / "status" / "mood_feedback.py"), "add", text,
                    "--source", "zirka"],
                   check=False, cwd=str(HOME), timeout=60,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send(bot: str, text: str) -> None:
    kind, role, _ = BOTS[bot]
    subprocess.run([str(HOME / "notify.sh"), "--bot", kind, "--voice-profile", role, text],
                   check=False, cwd=str(HOME), timeout=300)


def handle_update(bot: str, token: str, owner: str, st: dict, upd: dict,
                  dry_run: bool = False) -> int:
    """One update → zero or one answered message. Mutates st (offset is advanced by the
    caller); returns 1 when the message was answered."""
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return 0
    if str(msg.get("chat", {}).get("id")) != owner:
        log_dropped(bot, "чужий чат", upd)
        return 0
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text and msg.get("voice"):
        text = transcribe(token, msg["voice"]["file_id"])
        if text:
            print(f"{bot}: голосове розпізнано: {text[:80]}")
    if not text and msg.get("document"):
        text = read_document(token, msg["document"])
        if text:
            print(f"{bot}: документ прочитано: {len(text)} символів")
    if not text:
        log_dropped(bot, "без тексту", upd)
        return 0
    if not within_cap(st, bot):
        log_dropped(bot, "ліміт на годину", upd)
        print(f"{bot}: ліміт відповідей на годину вичерпано")
        return 0

    print(f"{bot} ← {text[:120]}")
    if dry_run:
        return 1
    search = ""
    if bot == "bruno":
        want = intent(text, st.get("last_scope", ""))
        if want["mode"] == "search":
            print(f"{bot}: пошук [{want['scope']}] {want['query']}")
            search = run_search(want["scope"], want["query"])
            st["last_scope"] = want["scope"]     # a follow-up inherits this area
    elif bot == "zirka":
        kind = zirka_kind(text)
        if kind["kind"] == "reference":
            print(f"{bot}: прогноз астролога ({kind.get('period')}) — вчусь")
            search = take_reference(text, kind)
        elif kind["kind"] == "feedback":
            record_feedback(text)
    try:
        reply = answer(bot, st.get("history", []), text, search)
    except Exception as e:                                               # noqa: BLE001
        print(f"{bot}: відповідь не склалась: {e}")
        return 0
    reply, request = split_handoff(reply)
    if not reply:
        return 0
    st.setdefault("history", []).append({"role": "user", "text": text})
    st["history"].append({"role": "bot", "text": reply})
    st.setdefault("answers", []).append(
        datetime.now().astimezone().isoformat(timespec="seconds"))
    send(bot, reply)
    print(f"{bot} → {reply[:120]}")
    if request:
        print(f"{bot}: передаю в головний чат: {request}")
        hand_over(bot, text, reply, request)
    return 1


def poll(bot: str, dry_run: bool = False) -> int:
    kind, _, _ = BOTS[bot]
    suffix = str(conf(f"telegram.bots.{kind}", "")).replace("-", "_").upper()
    env = env_telegram()
    token = env.get(f"TELEGRAM_BOT_TOKEN_{suffix}", "")
    if not token:
        print(f"{bot}: немає TELEGRAM_BOT_TOKEN_{suffix} — пропускаю")
        return 0
    owner = str(env.get(f"TELEGRAM_CHAT_ID_{suffix}") or env.get("TELEGRAM_CHAT_ID", ""))
    if not owner:
        print(f"{bot}: не знаю chat_id власника — пропускаю")
        return 0

    st = load_state(bot)
    try:
        res = api(token, "getUpdates", offset=st.get("offset", 0), timeout=0, limit=20)
    except Exception as e:                                               # noqa: BLE001
        print(f"{bot}: getUpdates не вдався: {e}")
        return 0
    if not res.get("ok"):
        print(f"{bot}: getUpdates відмовив: {str(res)[:200]}")
        return 0

    answered = 0
    for upd in res.get("result", []):
        st["offset"] = upd["update_id"] + 1
        # one bad update (a transcription timeout, a dead network, a hung notify.sh) must
        # not abort the batch: letting it escape skips save_state, and the next timer run
        # re-answers everything already sent (t1041). Logged and skipped instead.
        try:
            answered += handle_update(bot, token, owner, st, upd, dry_run)
        except Exception as e:                                           # noqa: BLE001
            print(f"{bot}: збій обробки повідомлення: {e}")
            log_dropped(bot, f"збій обробки: {e}", upd)

    # a dry run must not consume the queue: offsets are only committed when the messages
    # were actually answered (2026-10-30: a --dry-run swallowed a real question)
    if not dry_run:
        save_state(bot, st)
    return answered


def main() -> int:
    ap = argparse.ArgumentParser(description="відповіді в чатах окремих ботів")
    ap.add_argument("--bot", choices=sorted(BOTS), help="тільки цей бот")
    ap.add_argument("--dry-run", action="store_true", help="показати, нічого не слати")
    args = ap.parse_args()
    total = 0
    for bot in ([args.bot] if args.bot else sorted(BOTS)):
        total += poll(bot, args.dry_run)
    if not total:
        print("нічого нового")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
