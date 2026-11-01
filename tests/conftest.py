"""Shared test setup: put the repo root on sys.path so tests import project modules.

Run the suite with `.venv-voice/bin/pytest` from the repo root. Tests are fast and offline —
no network, no real Telegram, no ElevenLabs; stub those at the boundary instead.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "status", ROOT / "tasks", ROOT / "status" / "bots"):
    sys.path.insert(0, str(p))


import pytest                                                           # noqa: E402


@pytest.fixture(autouse=True)
def _restore_configuration():
    """Put the real configuration back after every test.

    Since t1109 `conf()` re-reads the config files when they change, so a test that repoints
    `noosconf.ROOT` at a temporary directory — several do — would otherwise leave the whole
    suite reading that tiny config for the next couple of seconds. Cheap, and it keeps the
    tests independent of their order.
    """
    yield
    import noosconf
    noosconf.reload()
