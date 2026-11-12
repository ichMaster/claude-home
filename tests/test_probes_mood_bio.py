"""t1061 — the horoscope and the biorhythms are two readings and must stay two.

Everything else in the design keeps them apart: two model calls, two messages, two voices,
and a biorhythm prompt forbidden to name a planet. The probe was the one place that glued
them back together, appending the three figures to the astrology summary.

The probes are scripts that run on import, so they are executed with `runpy` while
`noosconf.path` points at a temporary state file — no config file is touched.
"""
import io
import json
import runpy
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import noosconf

ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "status" / "probes"

TODAY = datetime.now(ZoneInfo("Europe/Kyiv")).date().isoformat()
STATE = {
    "day": TODAY,
    "biorhythms": "фізичний -0.63 (спадає) · емоційний -1.00 (низький)",
    "bio_conclusion": "Тіло просить спокою.",
    "summary": "Тон ставить Плутон. Місяць у Раку дає відновлення.",
}


def run(probe: str, state: dict, tmp_path: Path, monkeypatch) -> dict:
    f = tmp_path / "mood.json"
    f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(noosconf, "path", lambda *a, **k: f)
    buf = io.StringIO()
    with redirect_stdout(buf):
        runpy.run_path(str(PROBES / f"{probe}.py"), run_name="probe")
    return json.loads(buf.getvalue())


def test_mood_probe_carries_no_biorhythms(tmp_path, monkeypatch):
    """The astrology probe must not append the three figures to its text."""
    got = run("mood", STATE, tmp_path, monkeypatch)
    assert "Плутон" in got["text"]
    assert "фізичний" not in got["text"] and "Показники" not in got["text"]
    assert "biorhythms" not in got["value"]


def test_bio_probe_carries_no_astrology(tmp_path, monkeypatch):
    """And the biorhythm probe names no planet."""
    got = run("bio", STATE, tmp_path, monkeypatch)
    assert "фізичний" in got["text"]
    assert "Плутон" not in got["text"] and "Місяць" not in got["text"]
    assert got["id"] == "bio"


def test_both_say_so_when_the_morning_has_not_run(tmp_path, monkeypatch):
    stale = {**STATE, "day": "2000-01-01"}
    assert "ще не" in run("mood", stale, tmp_path, monkeypatch)["text"]
    assert "ще не" in run("bio", stale, tmp_path, monkeypatch)["text"]


def test_bio_without_a_conclusion_still_reports_the_figures(tmp_path, monkeypatch):
    got = run("bio", {**STATE, "bio_conclusion": ""}, tmp_path, monkeypatch)
    assert "фізичний" in got["text"] and got["value"]["fresh"] is True


# --- t1161: the --only bio run must leave today's figures where the probe looks -------------

def _bio_run(monkeypatch, tmp_path, existing_state):
    import sys
    sys.path.insert(0, str(ROOT / "status"))
    import mood
    f = tmp_path / "mood.json"
    f.write_text(json.dumps(existing_state, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mood, "state_path",
                        lambda key: f if key == "state" else tmp_path / key)
    monkeypatch.setattr(mood, "write_biorhythms",
                        lambda day, computed: {"figures": "", "conclusion": "Тіло просить спокою.",
                                               "raw": "сире"})
    monkeypatch.setattr(mood, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(mood, "send", lambda *a, **kw: None)
    monkeypatch.setattr(mood.sys, "argv", ["mood.py", "--only", "bio", "--day", TODAY])
    assert mood.main() == 0
    return json.loads(f.read_text(encoding="utf-8"))


def test_only_bio_updates_yesterdays_state(monkeypatch, tmp_path):
    """TC1 (t1161): the probe compares day to today — without this write it answers
    «ще не рахувались» every day v1 stays stopped."""
    st = _bio_run(monkeypatch, tmp_path,
                  {"day": "2026-11-01", "biorhythms": "старі цифри",
                   "bio_conclusion": "старе", "summary": "вчорашнє читання"})
    assert st["day"] == TODAY
    assert st["biorhythms"] and st["biorhythms"] != "старі цифри"
    assert st["bio_conclusion"] == "Тіло просить спокою."
    assert st.get("summary", "") == "", "вчорашнє астрочитання не сміє носити сьогоднішню дату"


def test_only_bio_keeps_todays_astrology(monkeypatch, tmp_path):
    """TC2 (t1161): today's summary already written → the bio run touches only its own half."""
    st = _bio_run(monkeypatch, tmp_path,
                  {"day": TODAY, "biorhythms": "", "bio_conclusion": "",
                   "summary": "сьогоднішнє читання"})
    assert st["day"] == TODAY
    assert st["summary"] == "сьогоднішнє читання"
    assert st["bio_conclusion"] == "Тіло просить спокою."
