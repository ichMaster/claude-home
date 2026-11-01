#!/usr/bin/env python3
"""The panel's password — one secret, hashed, set from a terminal.

    panel/auth.py set      prompt for a password and store its hash
    panel/auth.py clear    remove it (the terminal escape hatch out of a lockout)
    panel/auth.py show     say whether one is set, never what it is

One person, one machine, so there are no accounts and no roles (docs/features/ADMIN-PANEL.md
§ Phase 11). `hashlib.scrypt` comes with Python, so this adds no dependency, and the record
is stored as `scrypt$n$r$p$salt_hex$hash_hex` in `.env.panel`, mode 600, git-ignored.

Setting it belongs to the terminal and nowhere else: a request arriving over HTTP or Telegram
does not prove who sent it, which is the whole reason this file exists.
"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import os
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
RECORD_FILE = HOME / ".env.panel"
KEY = "PANEL_PASSWORD"

# scrypt's cost. 16384/8/1 is the classic interactive setting: ~0.1 s and 16 MB per attempt
# here, which is nothing for one login a day and a wall for a dictionary.
N, R, P, SALT_BYTES, KEY_LEN = 16384, 8, 1, 16, 32


def hash_password(password: str, salt: bytes | None = None) -> str:
    """`scrypt$n$r$p$salt$hash`. The salt is random, so two records of one password differ."""
    salt = salt or os.urandom(SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P,
                            dklen=KEY_LEN)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def check_password(password: str, record: str) -> bool:
    """Verify in constant time. A malformed record verifies nothing rather than raising —
    a panel that 500s on a corrupt password file is a panel nobody can log in to fix."""
    try:
        kind, n, r, p, salt_hex, want_hex = (record or "").split("$")
        if kind != "scrypt":
            return False
        salt, want = bytes.fromhex(salt_hex), bytes.fromhex(want_hex)
        if not salt or not want:
            return False
        got = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                             n=int(n), r=int(r), p=int(p), dklen=len(want))
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(got, want)


def stored_record() -> str:
    """The record from `.env.panel`, or "" — and "" must never be read as "open"."""
    try:
        for line in RECORD_FILE.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == KEY:
                return value.strip().strip("'\"")
    except OSError:
        return ""
    return ""


def save_record(record: str) -> None:
    """Write the record with the permissions it needs from the first byte: the file is
    created 600 before anything is written into it, not chmod-ed afterwards."""
    fd = os.open(RECORD_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"# the panel's password hash — set with panel/auth.py set\n"
                f"{KEY}={record}\n")
    os.chmod(RECORD_FILE, 0o600)


def clear_record() -> None:
    RECORD_FILE.unlink(missing_ok=True)


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "show"
    if what == "show":
        if stored_record():
            print("пароль встановлено")
        else:
            # The status without the next step left the owner re-running this and getting
            # the same line (2026-11-01, t1118).
            print("пароля немає — панель віддає лише сторінку входу.")
            print("щоб поставити:  ./panel/auth.py set")
        return 0
    if what == "clear":
        clear_record()
        print("пароль прибрано; панель тепер нікого не впускає, поки не поставиш новий")
        return 0
    if what != "set":
        print(__doc__)
        return 2
    first = getpass.getpass("новий пароль панелі: ")
    if len(first) < 8:
        print("замало — хоча б 8 знаків")
        return 1
    if first != getpass.getpass("ще раз: "):
        print("не збіглося")
        return 1
    save_record(hash_password(first))
    print(f"готово: {RECORD_FILE.name}, права 600. Сесії панелі скидаються рестартом:")
    print("  systemctl --user restart noos-panel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
