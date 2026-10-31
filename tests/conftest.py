"""Shared test setup: put the repo root on sys.path so tests import project modules.

Run the suite with `.venv-voice/bin/pytest` from the repo root. Tests are fast and offline —
no network, no real Telegram, no ElevenLabs; stub those at the boundary instead.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "status", ROOT / "tasks", ROOT / "status" / "bots"):
    sys.path.insert(0, str(p))
