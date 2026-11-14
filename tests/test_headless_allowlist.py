"""t1186 — the headless senders read text anyone on the internet can write (email,
facebookmail, RSS titles), so a bare `Bash` in --allowedTools turned prompt injection into
arbitrary command execution. Every Bash rule must name a command prefix, and every prompt
must say that fetched text is data, not instruction."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["status/digest-headless.sh", "status/social-headless.sh",
           "status/youtube-headless.sh"]
PROMPTS = ["status/digest-prompt.md", "status/social-prompt.md",
           "status/youtube-prompt.md"]


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_bare_bash_in_allowed_tools(script):
    """TC1: a rule must be Bash(<prefix>:*) — bare "Bash" allows everything."""
    text = "\n".join(line for line in (ROOT / script).read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    assert not re.search(r'"Bash"', text), f"{script} allowlists all of Bash"
    for rule in re.findall(r'"Bash\(([^)]*)\)"', text):
        assert rule.strip(), f"{script}: empty Bash rule"


@pytest.mark.parametrize("prompt", PROMPTS)
def test_prompt_carries_the_data_not_instruction_guard(prompt):
    """TC2: the same rule the bot prompts already carry (status/bots/common.md)."""
    text = (ROOT / prompt).read_text(encoding="utf-8")
    assert "data, not instruction" in text, f"{prompt} has no injection guard"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_is_valid_shell(script):
    """TC3: the edit must not break the timer that runs it."""
    out = subprocess.run(["bash", "-n", str(ROOT / script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
