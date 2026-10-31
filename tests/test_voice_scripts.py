"""t1042 — every curl in the voice scripts must carry a time bound: a stalled API
connection otherwise hangs notify.sh and with it every oneshot timer that speaks."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["voice/el_say.sh", "voice/dg_stt.sh", "voice/el_stt.sh"]


def curl_commands(text):
    """Each curl command as one logical line (backslash continuations joined)."""
    joined = text.replace("\\\n", " ")
    return [ln for ln in joined.splitlines() if re.search(r"(^|[=$(\s])curl\s", ln)]


@pytest.mark.parametrize("script", SCRIPTS)
def test_curl_has_max_time(script):
    cmds = curl_commands((ROOT / script).read_text())
    assert cmds, f"{script}: no curl found — did the script change shape?"
    for cmd in cmds:
        assert re.search(r"(--max-time|\s-m\s)", cmd), f"{script}: curl without --max-time: {cmd}"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_parses(script):
    subprocess.run(["bash", "-n", str(ROOT / script)], check=True)
