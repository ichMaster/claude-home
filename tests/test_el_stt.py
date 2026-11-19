"""t1212 — an ElevenLabs error body must never come back as the recognized text.

el_stt.sh printed `d.get("text") or json.dumps(d)` to stdout with exit 0, so during a
quota/key outage dg_stt.sh's short-clip fallback handed the raw error JSON to inbox.py
as the owner's words. The script runs with HOME pointed at a temp dir and curl stubbed
on PATH — nothing leaves the machine."""
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "voice" / "el_stt.sh"


def _run(tmp_path, curl_json):
    home = tmp_path / "home"
    (home / "claude-home").mkdir(parents=True)
    (home / "claude-home" / ".env.voice").write_text(
        "ELEVENLABS_API_KEY=dummy\n", encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    curl = bindir / "curl"
    curl.write_text("#!/usr/bin/env bash\ncat <<'EOF'\n" + curl_json + "\nEOF\n",
                    encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    audio = tmp_path / "a.oga"
    audio.write_bytes(b"xx")
    env = dict(os.environ, HOME=str(home), PATH=f"{bindir}:/usr/bin:/bin")
    return subprocess.run(["bash", str(SCRIPT), str(audio)],
                          capture_output=True, text=True, env=env)


def test_error_body_goes_to_stderr_not_stdout(tmp_path):
    """TC1: no `text` key — stderr + non-zero, never a fake transcript."""
    out = _run(tmp_path, '{"detail": {"status": "quota_exceeded"}}')
    assert out.returncode != 0
    assert out.stdout.strip() == ""
    assert "quota_exceeded" in out.stderr


def test_empty_transcript_is_an_answer(tmp_path):
    """TC2: recognized silence is an empty string, not the response JSON."""
    out = _run(tmp_path, '{"text": ""}')
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ""


def test_normal_transcript_unchanged(tmp_path):
    """TC3: the happy path still prints the text."""
    out = _run(tmp_path, '{"text": "привіт"}')
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "привіт"
