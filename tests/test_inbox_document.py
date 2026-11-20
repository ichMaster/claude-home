"""t1054 — a long reference arrives as a document whose mime Telegram chooses, not us:
whether it is text has to be decided from the bytes, and a drop has to say what it dropped.
"""
import json

import pytest

import inbox


@pytest.fixture
def fake_telegram(monkeypatch):
    """getFile + the file download, without the network. Returns the call log."""
    calls = {"getFile": 0, "download": 0, "payload": b""}

    def api(token, method, **params):
        calls["getFile"] += 1
        return {"ok": True, "result": {"file_path": "docs/x"}}

    class Resp:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(url, timeout=0):
        calls["download"] += 1
        return Resp(calls["payload"])

    monkeypatch.setattr(inbox, "api", api)
    monkeypatch.setattr(inbox.urllib.request, "urlopen", urlopen)
    return calls


def doc(**kw):
    return {"file_id": "f1", "file_name": "paste", "mime_type": "", "file_size": 100, **kw}


def test_unknown_mime_text_is_read(fake_telegram):
    """TC1: Telegram's long-paste file has no useful mime and no extension — read it."""
    fake_telegram["payload"] = "☽ Пн 26 жовтня\nМісяць у Тельці".encode("utf-8")
    got = inbox.read_document("t", doc(mime_type="application/octet-stream"))
    assert "Місяць у Тельці" in got


def test_binary_mime_not_downloaded(fake_telegram):
    """TC3: a picture or an archive is refused on its mime, before any download.
    Since t1218 the refusal is an exception that names itself, not an empty string."""
    for mime in ("image/png", "audio/ogg", "video/mp4", "application/pdf",
                 "application/zip"):
        with pytest.raises(inbox.DocumentRefused):
            inbox.read_document("t", doc(mime_type=mime))
    assert fake_telegram["download"] == 0


def test_binary_content_rejected(fake_telegram):
    """TC4: a .txt name on binary bytes must not reach the model as mojibake."""
    fake_telegram["payload"] = b"\x00\x01\x02\xff\xfe binary"
    with pytest.raises(inbox.DocumentRefused):
        inbox.read_document("t", doc(file_name="notes.txt"))


def test_oversized_document_ignored(fake_telegram):
    """TC5: the size cap holds, and nothing is fetched."""
    with pytest.raises(inbox.DocumentRefused):
        inbox.read_document("t", doc(file_size=10_000_000))
    assert fake_telegram["download"] == 0


def test_dropped_record_carries_the_shape(tmp_path, monkeypatch):
    """TC2: «без тексту» alone is unactionable — the record says what the message was."""
    monkeypatch.setattr(inbox, "STATE", tmp_path)
    upd = {"message": {"chat": {"id": 42}, "from": {"id": 42},
                       "document": {"file_name": "paste", "mime_type": "application/zip",
                                    "file_size": 1234}}}
    inbox.log_dropped("zirka", "без тексту", upd)
    rec = json.loads((tmp_path / "dropped.jsonl").read_text().splitlines()[-1])
    assert "document" in rec["shape"]["keys"]
    assert rec["shape"]["document"]["mime"] == "application/zip"
    assert rec["shape"]["document"]["size"] == 1234


# --- t1176: the argv limit --------------------------------------------------------------
# Linux caps one exec argument at 131072 bytes; a 150KB document passed whole made every
# model call raise E2BIG after the offset was saved — the message got no reply, ever.

def test_an_oversized_document_is_clamped_to_fit_argv(fake_telegram):
    """TC1: a 150KB paste must come back small enough to exec, with the cut named."""
    fake_telegram["payload"] = ("рядок тексту з довгого документа\n" * 3000).encode("utf-8")
    assert len(fake_telegram["payload"]) > 131072
    got = inbox.read_document("t", doc(file_size=len(fake_telegram["payload"])))
    assert got, "the document must still be read"
    assert len(got.encode("utf-8")) < 110000, "the body must fit an argv element with headroom"
    assert "обрізано" in got[-60:]


def test_a_document_inside_the_budget_is_untouched(fake_telegram):
    """TC2: the clamp must not touch a normal reference."""
    fake_telegram["payload"] = "☽ Пн 26 жовтня\nМісяць у Тельці".encode("utf-8")
    got = inbox.read_document("t", doc())
    assert got == "☽ Пн 26 жовтня\nМісяць у Тельці"


def test_the_clamp_survives_a_multibyte_boundary(fake_telegram):
    """TC3: cutting inside a Cyrillic character must not raise."""
    fake_telegram["payload"] = ("ї" * 120000).encode("utf-8")   # 2 bytes each
    got = inbox.read_document("t", doc(file_size=240000))
    assert got and "обрізано" in got[-60:]


# --- t1178: history re-expands clamped documents past the argv limit ----------------------
# The t1176 clamp bounded the incoming document, but the full clamped text was stored in
# history and re-embedded in every later prompt — two large documents left ~125KB of history
# that made every exec fail E2BIG, and history only rotates on success, so the bot bricked.

def test_call_claude_sends_the_prompt_on_stdin(monkeypatch):
    """TC1: no prompt byte travels as an argv element, so no size can raise E2BIG."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")

        class Out:
            returncode = 0
            stdout = "ок"
            stderr = ""
        return Out()

    monkeypatch.setattr(inbox.subprocess, "run", fake_run)
    prompt = "довгий промпт " * 20000          # ~0.5MB, far past MAX_ARG_STRLEN
    assert inbox.call_claude(prompt) == "ок"
    assert all(len(arg.encode("utf-8")) < 131072 for arg in seen["cmd"])
    assert prompt not in seen["cmd"]
    assert seen["input"] == prompt


def test_history_entries_are_clipped():
    """TC2: a stored turn is bounded, with the cut named; short ones pass untouched."""
    big = "рядок із великого документа\n" * 5000
    clipped = inbox.clip_entry(big)
    assert len(clipped.encode("utf-8")) <= 8192 + 80
    assert "обрізано" in clipped[-60:]
    assert inbox.clip_entry("коротка репліка") == "коротка репліка"


def test_clip_entry_survives_a_multibyte_boundary():
    """TC3: cutting inside a Cyrillic character must not raise or produce mojibake."""
    clipped = inbox.clip_entry("ї" * 9000)    # 2 bytes each — the cut lands mid-character
    assert clipped.encode("utf-8").decode("utf-8")
    assert "обрізано" in clipped[-60:]


# --- t1213: a transient getFile error must not consume the document silently -----------

def _doc_update(caption=""):
    msg = {"chat": {"id": 42}, "document": doc()}
    if caption:
        msg["caption"] = caption
    return {"update_id": 1, "message": msg}


def _broken_telegram(monkeypatch, sent):
    def api(token, method, **params):
        raise inbox.urllib.error.URLError("timed out")
    monkeypatch.setattr(inbox, "api", api)
    monkeypatch.setattr(inbox, "send", lambda bot, text, **k: sent.append(text))
    monkeypatch.setattr(inbox, "log_dropped", lambda *a, **k: None)
    monkeypatch.setattr(inbox, "answer", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("answer() must not run for a lost document")))


def test_getfile_failure_sends_a_notice(monkeypatch):
    """TC1: one network hiccup — the loss is said out loud, not raised past the offset."""
    sent = []
    _broken_telegram(monkeypatch, sent)
    st = {}
    got = inbox.handle_update("zirka", "t", "42", st, _doc_update())
    assert got == 0
    assert sent and "окумент" in sent[0]


def test_getfile_failure_wins_over_the_caption(monkeypatch):
    """TC2: answering the caption while dropping the body is the silent loss again."""
    sent = []
    _broken_telegram(monkeypatch, sent)
    st = {}
    inbox.handle_update("zirka", "t", "42", st, _doc_update(caption="це на завтра"))
    assert sent and "окумент" in sent[0]


# --- t1217: the download leg and a not-ok getFile reach the t1213 guard too --------------

def test_download_failure_sends_a_notice(monkeypatch):
    """TC1: getFile succeeds, the download times out — the loss is said, not swallowed."""
    sent = []

    def api(token, method, **params):
        return {"ok": True, "result": {"file_path": "docs/x"}}

    def urlopen(url, timeout=0):
        raise inbox.urllib.error.URLError("timed out")

    monkeypatch.setattr(inbox, "api", api)
    monkeypatch.setattr(inbox.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(inbox, "send", lambda bot, text, **k: sent.append(text))
    monkeypatch.setattr(inbox, "log_dropped", lambda *a, **k: None)
    monkeypatch.setattr(inbox, "answer", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("answer() must not run for a lost document")))
    st = {}
    got = inbox.handle_update("zirka", "t", "42", st, _doc_update(caption="це на завтра"))
    assert got == 0
    assert sent and "окумент" in sent[0]


def test_getfile_not_ok_raises(monkeypatch):
    """TC2: a 200 body with ok:false is a failure, not an empty document."""
    monkeypatch.setattr(inbox, "api",
                        lambda token, method, **p: {"ok": False, "description": "bad"})
    with pytest.raises(Exception):
        inbox.read_document("t", doc())


# --- t1218: a deliberate refusal (size, binary) is said out loud, not silence ------------

def test_oversized_document_sends_a_named_notice(monkeypatch, fake_telegram):
    """TC1: the size refusal reaches the chat and the caption is not answered alone."""
    sent, dropped = [], []
    monkeypatch.setattr(inbox, "send", lambda bot, text, **k: sent.append(text))
    monkeypatch.setattr(inbox, "log_dropped",
                        lambda bot, why, upd: dropped.append(why))
    monkeypatch.setattr(inbox, "answer", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("answer() must not run for a refused document")))
    msg = {"chat": {"id": 42}, "caption": "це на завтра",
           "document": doc(file_size=10_000_000)}
    got = inbox.handle_update("zirka", "t", "42", {}, {"update_id": 1, "message": msg})
    assert got == 0
    assert sent and "завеликий" in sent[0]
    assert dropped and "відхилено" in dropped[0]


def test_binary_mime_refusal_carries_a_notice(fake_telegram):
    """TC2: a PDF raises a refusal with a user-facing notice, before any download."""
    with pytest.raises(inbox.DocumentRefused) as e:
        inbox.read_document("t", doc(mime_type="application/pdf"))
    assert e.value.notice
    assert fake_telegram["download"] == 0


def test_binary_bytes_refusal_carries_a_notice(fake_telegram):
    """TC3: binary bytes under a .txt name raise the same refusal after the download."""
    fake_telegram["payload"] = b"\x00\x01\x02\xff\xfe binary"
    with pytest.raises(inbox.DocumentRefused) as e:
        inbox.read_document("t", doc(file_name="notes.txt"))
    assert e.value.notice
