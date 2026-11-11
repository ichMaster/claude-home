"""t1149 — every message says when it was sent.

He listens to Telegram rather than reading it, often hours later, so the timestamp on the
screen is not in the audio. The spoken form is pure Ukrainian words: a digit handed to the
synthesizer comes back in the wrong case.
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "status" / "tools"))

from timestamp import day_words, minute_words, stamp                    # noqa: E402

LATIN = re.compile(r"[A-Za-z]")
DIGIT = re.compile(r"[0-9]")


# --- TC1-TC7: the two forms --------------------------------------------------------------

def test_both_forms_of_one_moment():
    written, spoken = stamp(datetime(2026, 11, 12, 11, 5))
    assert written == "12 листопада, 11:05"
    assert spoken == "Дванадцяте листопада, одинадцята година п'ять хвилин."


def test_the_spoken_form_is_words_only():
    _, spoken = stamp(datetime(2026, 11, 12, 11, 5))
    assert not LATIN.search(spoken), "a Latin letter is read out as a foreign word"
    assert not DIGIT.search(spoken), "a digit comes back in the wrong case"


def test_no_year_anywhere():
    written, spoken = stamp(datetime(2026, 11, 12, 11, 5))
    assert "2026" not in written and "26" not in written
    assert "двадцять шостий" not in spoken and "рік" not in spoken


def test_a_whole_hour_says_so():
    assert stamp(datetime(2026, 11, 12, 11, 0))[1].endswith("одинадцята година рівно.")


@pytest.mark.parametrize("minute,expected", [
    (1, "одна хвилина"), (2, "дві хвилини"), (4, "чотири хвилини"), (5, "п'ять хвилин"),
    (11, "одинадцять хвилин"), (12, "дванадцять хвилин"), (14, "чотирнадцять хвилин"),
    (20, "двадцять хвилин"), (21, "двадцять одна хвилина"), (22, "двадцять дві хвилини"),
    (25, "двадцять п'ять хвилин"), (59, "п'ятдесят дев'ять хвилин"),
])
def test_minutes_agree_in_ukrainian(minute, expected):
    assert minute_words(minute) == expected


def test_midnight_is_never_a_zero():
    assert stamp(datetime(2026, 11, 12, 0, 30))[1] == \
        "Дванадцяте листопада, дванадцята година тридцять хвилин ночі."
    assert stamp(datetime(2026, 11, 12, 0, 0))[1] == "Дванадцяте листопада, опівночі."


def test_every_day_and_every_minute_speak():
    """A sweep, so a hole in a table is found here and not in a voice message."""
    for day in range(1, 32):
        assert day_words(day) and not DIGIT.search(day_words(day))
    for hour in range(24):
        for minute in range(60):
            _, spoken = stamp(datetime(2026, 1, 15, hour, minute))
            assert not DIGIT.search(spoken) and not LATIN.search(spoken)
            assert spoken.endswith(".")


# --- TC8-TC10: notify.sh carries it ------------------------------------------------------

def fake_home(tmp_path):
    """A notify.sh that can run: real script, stubbed network, voice and log."""
    home = tmp_path / "home"
    repo = home / "claude-home"
    (repo / "voice").mkdir(parents=True)
    (repo / "status" / "tools").mkdir(parents=True)
    shutil.copy(ROOT / "notify.sh", repo / "notify.sh")
    shutil.copy(ROOT / "config.sh", repo / "config.sh")
    shutil.copy(ROOT / "config.json", repo / "config.json")
    (repo / "status" / "tools" / "timestamp.py").symlink_to(
        ROOT / "status" / "tools" / "timestamp.py")
    (repo / ".venv-voice").symlink_to(ROOT / ".venv-voice")
    (repo / ".env.telegram").write_text(
        "TELEGRAM_BOT_TOKEN=stub\nTELEGRAM_CHAT_ID=0\n", encoding="utf-8")

    # the Sent log writes into the real repo through noosconf — stub it out entirely
    (repo / "status" / "tools" / "sent_log.py").write_text("import sys; sys.stdin.read()\n",
                                                           encoding="utf-8")
    (repo / "voice" / "el_say.sh").write_text(
        '#!/usr/bin/env bash\nout="$1"; shift\nprintf "%s" "$*" > "$HOME/spoken.txt"\n'
        ': > "$out"\n', encoding="utf-8")
    (repo / "voice" / "el_say.sh").chmod(0o755)
    (repo / "voice" / "to_ogg.py").write_text(
        "import sys, pathlib; pathlib.Path(sys.argv[2]).write_bytes(b'x')\n", encoding="utf-8")

    binp = home / "bin"
    binp.mkdir()
    (binp / "curl").write_text(
        '#!/usr/bin/env bash\n'
        'for a in "$@"; do case "$a" in text=*) printf "%s\\n---\\n" "${a#text=}" '
        '>> "$HOME/text.log";; esac; done\n'
        'case "$*" in *sendVoice*) echo voice >> "$HOME/voice.log";; esac\n'
        'echo 200\n', encoding="utf-8")
    (binp / "curl").chmod(0o755)
    return home, repo, binp


def run_notify(tmp_path, args):
    home, repo, binp = fake_home(tmp_path)
    env = dict(os.environ, HOME=str(home), PATH=f"{binp}:{os.environ['PATH']}")
    proc = subprocess.run(["bash", str(repo / "notify.sh"), *args],
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    sent = (home / "text.log")
    spoken = (home / "spoken.txt")
    return (sent.read_text(encoding="utf-8") if sent.exists() else "",
            spoken.read_text(encoding="utf-8") if spoken.exists() else "")


def today_written():
    return stamp()[0]


@pytest.mark.parametrize("args,in_text,in_voice", [
    (["привіт"], True, True),
    (["--no-voice", "привіт"], True, False),
    (["--voice-only", "привіт"], False, True),
    (["--voice-text", "коротко", "довгий текст"], True, True),
])
def test_notify_stamps_both_halves(tmp_path, args, in_text, in_voice):
    text, spoken = run_notify(tmp_path, args)
    written = today_written()
    assert (written in text) is in_text, f"written stamp in the text part: {text!r}"
    if in_voice:
        assert spoken.startswith(stamp()[1][:20]), f"spoken stamp missing: {spoken!r}"
        assert not DIGIT.search(spoken.splitlines()[0])
    if not in_text:
        assert text == ""


def test_no_stamp_sends_what_it_was_given(tmp_path):
    text, spoken = run_notify(tmp_path, ["--no-stamp", "привіт"])
    assert text.strip().startswith("привіт")
    assert spoken.strip() == "привіт"


def test_a_split_message_is_stamped_once(tmp_path):
    long = "\n\n".join(["абзац " + "я" * 200 for _ in range(30)])
    text, _ = run_notify(tmp_path, ["--no-voice", long])
    assert text.count("---\n") > 1, "the message did not split — the test proves nothing"
    assert text.count(today_written()) == 1
