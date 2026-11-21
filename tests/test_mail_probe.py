"""t1045 — the mail probe must not hang without a timeout and must not skip mail past the
per-run batch cap: the un-fetched remainder has to surface on the next run."""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status" / "probes"))

mail = importlib.import_module("mail")


def test_pick_batch_overflow_resurfaces_next_run():
    """TC1: oldest first; last_uid covers only the fetched batch, so `> last_uid` finds the
    remainder next run instead of skipping it forever."""
    uids = [str(u).encode() for u in range(1, 101)]
    batch, last, remaining = mail.pick_batch(uids, cap=60)
    assert batch == uids[:60]
    assert last == 60
    assert remaining == 40
    assert [u for u in uids if int(u) > last] == uids[60:]


def test_pick_batch_small():
    """TC3: under the cap everything is fetched and nothing is left over."""
    uids = [b"7", b"9"]
    batch, last, remaining = mail.pick_batch(uids, cap=60)
    assert batch == uids and last == 9 and remaining == 0


def test_imap_opened_with_timeout(monkeypatch, tmp_path):
    """TC2: a blackholed connection must fail within a deadline, not hang the caller."""
    captured = {}

    class FakeIMAP:
        def __init__(self, host, port, **kw):
            captured.update(kw)
            raise mail.imaplib.IMAP4.error("stop here")

    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setattr(mail, "env", lambda: {"GMAIL_USER": "u", "GMAIL_APP_PASSWORD": "p"})
    monkeypatch.setattr(mail, "STATE", tmp_path / "mail.json")
    with pytest.raises(SystemExit):
        mail.main()
    assert captured.get("timeout"), "IMAP4_SSL opened without a timeout"


# --- t1226: corrupt state reads as a fresh install, never a dead probe ------------------

def _fresh_install_imap(monkeypatch, tmp_path, state_text):
    """Run main() with a state file holding `state_text`; capture that the probe got as
    far as opening IMAP (i.e. past the state read) instead of dying on it."""
    reached = {}

    class FakeIMAP:
        def __init__(self, host, port, **kw):
            reached["imap"] = True
            raise mail.imaplib.IMAP4.error("stop here")

    state = tmp_path / "mail.json"
    state.write_text(state_text)
    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setattr(mail, "env", lambda: {"GMAIL_USER": "u", "GMAIL_APP_PASSWORD": "p"})
    monkeypatch.setattr(mail, "STATE", state)
    with pytest.raises(SystemExit):
        mail.main()
    return reached


def test_garbage_state_file_does_not_kill_the_probe(monkeypatch, tmp_path):
    """t1226 TC1: a torn mail.json must read as a fresh install, not JSONDecodeError."""
    reached = _fresh_install_imap(monkeypatch, tmp_path, "{broken")
    assert reached.get("imap"), "the probe died on the state read, before IMAP"


def test_non_int_last_uid_does_not_kill_the_probe(monkeypatch, tmp_path):
    """t1226 TC2: a non-numeric last_uid must read as a fresh install, not ValueError."""
    reached = _fresh_install_imap(monkeypatch, tmp_path, '{"last_uid": "sure"}')
    assert reached.get("imap"), "the probe died on the state read, before IMAP"


def test_valid_state_still_yields_its_uid(monkeypatch, tmp_path):
    """t1226 TC3: a healthy state file keeps working."""
    state = tmp_path / "mail.json"
    state.write_text('{"last_uid": 42}')
    monkeypatch.setattr(mail, "STATE", state)
    st, last = mail.load_state()
    assert last == 42 and st.get("last_uid") == 42
