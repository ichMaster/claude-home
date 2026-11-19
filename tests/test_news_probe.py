"""t1170 — a torn news seen-state file must not kill the topic.

The seen file is parsed before the probe's try block and rewritten non-atomically, so one
power cut mid-write used to make every later run of that topic crash before printing
anything — the topic silently vanished from the digest until the file was deleted by hand.

The probe is a script that runs on import, so it is executed with `runpy` while
`noosconf.path` points at a temporary directory and the network is a canned RSS answer.
"""
import io
import json
import runpy
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import noosconf

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "status" / "probes" / "news.py"

RSS = """<rss><channel>
<item><title>Тестова новина про випробування - Джерело</title>
<link>https://example.com/a</link>
<source url="https://example.com">Джерело</source></item>
</channel></rss>"""


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return RSS.encode("utf-8")


def run(tmp_path, monkeypatch, seen_text=None):
    status = tmp_path / "status"
    (status / "topics").mkdir(parents=True, exist_ok=True)
    (status / "state").mkdir(parents=True, exist_ok=True)
    (status / "topics" / "demo.json").write_text(json.dumps(
        {"назва": "Демо", "запит": "випробування", "ліміт": 5}, ensure_ascii=False),
        encoding="utf-8")
    if seen_text is not None:
        (status / "state" / "news-demo.json").write_text(seen_text, encoding="utf-8")
    monkeypatch.setattr(noosconf, "path", lambda *a, **k: tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setattr("sys.argv", ["news.py", "demo"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        runpy.run_path(str(PROBE), run_name="probe")
    return json.loads(buf.getvalue()), status / "state" / "news-demo.json"


def test_torn_seen_file_does_not_kill_the_topic(tmp_path, monkeypatch):
    """TC1: truncated JSON from a power cut — the probe must still answer."""
    out, _ = run(tmp_path, monkeypatch, seen_text='["abc123", "def45')
    assert out["ok"] is True
    assert out["value"]["items"], "the fetched item must be reported"


def test_seen_file_is_rewritten_valid(tmp_path, monkeypatch):
    """TC2: after the run the state file holds the new key and parses."""
    out, seen_file = run(tmp_path, monkeypatch, seen_text='["abc123", "def45')
    keys = json.loads(seen_file.read_text(encoding="utf-8"))
    assert out["value"]["items"][0]["key"] in keys


def test_healthy_seen_file_still_filters(tmp_path, monkeypatch):
    """TC3: an already-seen link is not reported again."""
    import hashlib
    key = hashlib.sha1(b"https://example.com/a").hexdigest()[:12]
    out, _ = run(tmp_path, monkeypatch, seen_text=json.dumps([key]))
    assert out["value"]["items"] == []
    assert out["severity"] == "quiet"


def test_trim_keeps_recent_keys_not_sort_winners(tmp_path, monkeypatch):
    """t1209 TC1: with the seen file full of keys that sort above the new story's hash
    (c4ed1c218d14), the freshly added key must survive the trim — before the fix
    sorted(seen)[-800:] evicted it and the same story came back as new every poll."""
    full = json.dumps([f"ffffffff{i:04d}" for i in range(800)])
    out1, state = run(tmp_path, monkeypatch, seen_text=full)
    assert out1["value"]["items"], "first run should report the story"
    kept = json.loads(state.read_text())
    assert "c4ed1c218d14" in kept, "the fresh key was evicted by the trim"

    out2, _ = run(tmp_path, monkeypatch, seen_text=state.read_text())
    assert not out2["value"]["items"], "the story was re-reported after the trim"


def test_trim_evicts_oldest_at_cap(tmp_path, monkeypatch):
    """t1209 TC2: the cap evicts from the head (oldest), keeps 800."""
    full = json.dumps([f"ffffffff{i:04d}" for i in range(800)])
    _, state = run(tmp_path, monkeypatch, seen_text=full)
    kept = json.loads(state.read_text())
    assert len(kept) == 800
    assert "ffffffff0000" not in kept          # oldest evicted
    assert kept[-1] == "c4ed1c218d14"          # newest at the tail
