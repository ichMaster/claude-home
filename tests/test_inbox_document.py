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
    """TC3: a picture or an archive is refused on its mime, before any download."""
    for mime in ("image/png", "audio/ogg", "video/mp4", "application/pdf",
                 "application/zip"):
        assert inbox.read_document("t", doc(mime_type=mime)) == ""
    assert fake_telegram["download"] == 0


def test_binary_content_rejected(fake_telegram):
    """TC4: a .txt name on binary bytes must not reach the model as mojibake."""
    fake_telegram["payload"] = b"\x00\x01\x02\xff\xfe binary"
    assert inbox.read_document("t", doc(file_name="notes.txt")) == ""


def test_oversized_document_ignored(fake_telegram):
    """TC5: the size cap holds, and nothing is fetched."""
    assert inbox.read_document("t", doc(file_size=10_000_000)) == ""
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
