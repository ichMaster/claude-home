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


def _code(script):
    return "\n".join(line for line in (ROOT / script).read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_auto_approved_edits(script):
    """t1207 TC1: acceptEdits auto-approves Write/Edit, which --allowedTools does not
    restrict — an injected mail could persist instructions into repo files the trusted
    session later obeys. The write tools must be disallowed explicitly."""
    text = _code(script)
    assert "acceptEdits" not in text, f"{script} auto-approves Write/Edit on untrusted input"
    assert "--disallowedTools" in text, f"{script} does not disallow the write tools"
    for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        assert f'"{tool}"' in text, f"{script} does not disallow {tool}"


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_secret_reading_helpers(script):
    """t1207 TC2: Bash(cat:*) matches `cat .env.telegram` — a secret in the transcript."""
    rules = re.findall(r'"Bash\(([^)]*)\)"', _code(script))
    for rule in rules:
        prefix = rule.split(":")[0].strip()
        assert prefix not in ("cat", "head", "tail"), \
            f"{script}: Bash({rule}) reaches the secret files"


def test_settings_deny_read_on_secrets():
    """t1207 TC3: the built-in Read tool is allowed by default in headless runs, so the
    shared settings file must fence it off the env files and credentials."""
    import json
    settings = json.loads((ROOT / "status/digest-settings.json").read_text(encoding="utf-8"))
    deny = settings.get("permissions", {}).get("deny", [])
    for pattern in ("Read(./.env*)", "Read(./config.local.json)",
                    "Read(~/.claude/.credentials.json)", "Read(~/.claude/.env.oauth)"):
        assert pattern in deny, f"digest-settings.json does not deny {pattern}"


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_write_capable_bash_prefixes(script):
    """t1220 TC1: a redirection rides inside the allowed command — Bash(echo:*) approves
    `echo '…' >> CLAUDE.md`, re-opening the persistence channel t1207 closed."""
    rules = re.findall(r'"Bash\(([^)]*)\)"', _code(script))
    for rule in rules:
        prefix = rule.split(":")[0].strip()
        assert prefix not in ("echo", "printf", "tee", "dd", "sed", "cp", "mv", "touch",
                              "ln", "install"), \
            f"{script}: Bash({rule}) can write files via redirection or by design"
