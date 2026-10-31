"""t1047 — one torn line in mood-feedback.jsonl (multiple appenders, no locking) must not
break ask/list/calibrate forever: remarks() skips what it cannot parse."""
import importlib
from datetime import date

import mood_feedback as mf


def test_remarks_skip_corrupt_line(monkeypatch, tmp_path):
    f = tmp_path / "mood-feedback.jsonl"
    f.write_text('{"day": "2026-10-30", "text": "перший"}\n'
                 '{"day": "2026-10-30", "text": "обірва',
                 encoding="utf-8")
    with f.open("a", encoding="utf-8") as fh:
        fh.write('\n{"day": "2026-10-31", "text": "другий"}\n')
    monkeypatch.setattr(mf, "feedback_file", lambda: f)
    rows = mf.remarks()
    assert [r["text"] for r in rows] == ["перший", "другий"]
    assert [r["text"] for r in mf.remarks(date(2026, 10, 31))] == ["другий"]
