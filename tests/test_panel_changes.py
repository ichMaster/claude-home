"""t1062 — admin panel, phase 2. The screen's one duty is to make an unchecked commit
look unchecked, so most of these tests are about absences being named rather than blank.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import changes                                                          # noqa: E402
import render                                                           # noqa: E402

LOG = "\x1f".join(["a" * 40, "2026-10-31T12:00:00+02:00", "fix(panel): щось (t1055)", "Я"]) \
    + "\n" + "\x1f".join(["b" * 40, "2026-10-30T09:00:00+02:00", "chore: без задачі", "Я"])


# --- TC1: commits -----------------------------------------------------------------------

def test_commit_rows_parse_the_log():
    rows = changes.commit_rows(LOG, ahead={"a" * 40})
    assert rows[0]["task"] == "t1055" and rows[0]["no_task"] is False
    assert rows[0]["local"] is True and rows[0]["short"] == "aaaaaaa"
    assert rows[0]["date"] == "2026-10-31 12:00"


def test_commit_without_a_task_id_is_flagged():
    """The process says there should not be one, so the screen has to show it."""
    rows = changes.commit_rows(LOG)
    assert rows[1]["no_task"] is True and rows[1]["task"] == ""
    assert rows[1]["local"] is False


def test_garbage_lines_are_skipped_not_fatal():
    assert changes.commit_rows("not a log line\n\n") == []


# --- TC2, TC3: what is behind a commit ----------------------------------------------------

def test_detail_finds_the_spec_and_tests(monkeypatch, tmp_path):
    specs, tests = tmp_path / "specs", tmp_path / "tests"
    specs.mkdir(); tests.mkdir()
    (specs / "t1055.md").write_text("# t1055", encoding="utf-8")
    (tests / "test_panel.py").write_text("# covers t1055", encoding="utf-8")
    (tests / "test_other.py").write_text("# unrelated", encoding="utf-8")
    monkeypatch.setattr(changes, "SPECS", specs)
    monkeypatch.setattr(changes, "TESTS", tests)
    monkeypatch.setattr(changes, "HOME", tmp_path)
    got = changes.commit_detail({"sha": "a" * 40, "task": "t1055"},
                                {"t1055": {"title": "фаза 1"}})
    assert got["spec"].endswith("t1055.md")
    assert got["tests"] == ["test_panel.py"]
    assert got["task_title"] == "фаза 1"


def test_missing_spec_is_reported_not_invented(monkeypatch, tmp_path):
    monkeypatch.setattr(changes, "SPECS", tmp_path / "specs")
    monkeypatch.setattr(changes, "TESTS", tmp_path / "tests")
    got = changes.commit_detail({"sha": "a" * 40, "task": "t9999"})
    assert got["spec"] is None and got["tests"] == []


def test_security_reading_present_and_absent_differ(monkeypatch, tmp_path):
    monkeypatch.setattr(changes, "SPECS", tmp_path)
    monkeypatch.setattr(changes, "TESTS", tmp_path)
    monkeypatch.setattr(changes, "COMMIT_REVIEW", tmp_path / "review")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / f"{'a' * 40}.md").write_text("нічого чутливого", encoding="utf-8")
    assert "чутливого" in changes.commit_detail({"sha": "a" * 40, "task": ""})["review"]
    assert changes.commit_detail({"sha": "b" * 40, "task": ""})["review"] is None


# --- t1064: push state ----------------------------------------------------------------------

class _Run:
    def __init__(self, rc, out=""):
        self.returncode, self.stdout = rc, out


def test_ahead_is_unknown_when_the_remote_ref_fails(monkeypatch):
    """t1064: a failed rev-list (no origin/main, git error) must answer None, not 'zero'."""
    monkeypatch.setattr(changes.subprocess, "run", lambda *a, **k: _Run(128))
    assert changes.ahead_hashes() is None
    monkeypatch.setattr(changes.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    assert changes.ahead_hashes() is None


def test_ahead_still_counts_when_the_ref_answers(monkeypatch):
    monkeypatch.setattr(changes.subprocess, "run",
                        lambda *a, **k: _Run(0, "a" * 40 + "\n"))
    assert changes.ahead_hashes() == {"a" * 40}
    monkeypatch.setattr(changes.subprocess, "run", lambda *a, **k: _Run(0, ""))
    assert changes.ahead_hashes() == set()


def test_unknown_push_state_is_not_rendered_as_pushed():
    """t1064: «Усе запушено» may only mean a verified zero."""
    html = render.render_changes([], {}, [], [], None, [])
    assert "Усе запушено" not in html and "невідом" in html
    assert "Усе запушено" in render.render_changes([], {}, [], [], 0, [])
    assert changes.commit_rows(LOG, ahead=None)[0]["local"] is False


# --- TC4: the nightly reviews --------------------------------------------------------------

SCAN = """# Nightly review

## High

### H1 — everything is on fire (a.py:1)

## Medium

### M1 — probes always stale (panel/data.py:41)
### M2 — a collector blanks the page (panel/data.py:106)

## Low (reported, not fixed)

### L1 — a naive timestamp (panel/data.py:50)
"""


def test_findings_counted_by_severity():
    got = changes.findings(SCAN)
    assert len(got["high"]) == 1 and len(got["medium"]) == 2 and len(got["low"]) == 1
    assert got["medium"][0].startswith("M1")


def test_unrecognised_report_is_not_guessed_at():
    assert changes.findings("just some prose with no headings") == {}


def test_a_section_after_low_is_not_counted_as_low():
    """t1063: the real scans end with `## Checked and cleared` — its entries are cleared
    non-findings and must not leak into the Low count or the standing Low list."""
    report = (SCAN + "\n## Checked and cleared\n\n"
              "### Path traversal — verified safe\n### XSS — verified safe\n")
    got = changes.findings(report)
    assert got["low"] == ["L1 — a naive timestamp (panel/data.py:50)"]
    assert all("verified safe" not in t for ts in got.values() for t in ts)


def test_nights_pair_scan_with_fixes(tmp_path):
    (tmp_path / "2026-10-31-scan.md").write_text(SCAN, encoding="utf-8")
    (tmp_path / "2026-10-31-fixes.md").write_text("fixed both", encoding="utf-8")
    (tmp_path / "last.txt").write_text("abc", encoding="utf-8")       # not a report
    nights = changes.review_nights(tmp_path)
    assert len(nights) == 1
    assert nights[0]["counts"] == {"high": 1, "medium": 2, "low": 1}
    assert nights[0]["fixes"] == "fixed both" and nights[0]["parsed"] is True


def test_missing_report_dir(tmp_path):
    assert changes.review_nights(tmp_path / "nope") == []


# --- t1065: torn files must not 500 the page -------------------------------------------------

def test_a_torn_report_does_not_raise(tmp_path):
    """t1065: the nightly review writes multi-byte Ukrainian while the panel reads — a read
    landing mid-character must cost a replacement char, not the whole screen."""
    (tmp_path / "2026-10-30-scan.md").write_bytes("## Low\n### Б".encode("utf-8")[:-1])
    nights = changes.review_nights(tmp_path)
    assert len(nights) == 1 and nights[0]["date"] == "2026-10-30"


def test_a_torn_security_reading_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setattr(changes, "SPECS", tmp_path)
    monkeypatch.setattr(changes, "TESTS", tmp_path)
    monkeypatch.setattr(changes, "COMMIT_REVIEW", tmp_path / "review")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / f"{'a' * 40}.md").write_bytes("нічого".encode("utf-8")[:-1])
    got = changes.commit_detail({"sha": "a" * 40, "task": ""})
    assert got["review"]                               # present, even if torn


def test_an_unreadable_security_reading_is_absent_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(changes, "SPECS", tmp_path)
    monkeypatch.setattr(changes, "TESTS", tmp_path)
    monkeypatch.setattr(changes, "COMMIT_REVIEW", tmp_path / "review")
    (tmp_path / "review").mkdir()
    f = tmp_path / "review" / f"{'a' * 40}.md"
    f.write_text("x", encoding="utf-8")
    f.chmod(0)
    try:
        got = changes.commit_detail({"sha": "a" * 40, "task": ""})
    finally:
        f.chmod(0o644)
    assert got["review"] is None


# --- TC5: the standing Low list ------------------------------------------------------------

def test_lows_accumulate_and_keep_the_first_night(tmp_path):
    (tmp_path / "2026-10-29-scan.md").write_text(SCAN, encoding="utf-8")
    (tmp_path / "2026-10-31-scan.md").write_text(SCAN, encoding="utf-8")
    lows = changes.open_lows(changes.review_nights(tmp_path))
    assert len(lows) == 1, "the same finding twice is one item, not two"
    assert lows[0]["since"] == "2026-10-29"
    assert lows[0]["nights"] == 2


# --- t1066: the change-log search -------------------------------------------------------------

def test_search_matches_only_what_the_table_shows():
    """t1066: the record also carries cwd and session, where '/home/ich' and hex ids make
    every common needle match every row."""
    rows = [{"ts": "2026-10-31T10:00:00", "kind": "bash", "target": "restart.sh",
             "detail": "перезапуск", "session": "deadbeef", "cwd": "/home/ich/claude-home"}]
    assert changes.filter_changes(rows, "ich") == []
    assert changes.filter_changes(rows, "deadbeef") == []
    assert changes.filter_changes(rows, "RESTART") == rows
    assert changes.filter_changes(rows, "перезапуск") == rows
    assert changes.filter_changes(rows, "") == rows


def test_search_miss_is_named_not_disguised_as_an_empty_day():
    """t1066: nothing matching a query is «нічого не знайдено», not «записів немає»."""
    html = render.render_changes([], {}, [], [], 0, [], query="xyz")
    assert "Нічого не знайдено" in html and "записів немає" not in html
    assert "записів немає" in render.render_changes([], {}, [], [], 0, [], query="")


def test_search_reads_a_wider_window_than_the_plain_view(monkeypatch):
    """t1066: one day already holds 484 records; a search over 200 silently lies."""
    import server
    calls = []
    monkeypatch.setattr(server.data, "recent_changes",
                        lambda n: calls.append(n) or [])
    monkeypatch.setattr(server.changes, "git", lambda *a: "")
    monkeypatch.setattr(server.changes, "ahead_hashes", lambda: set())
    monkeypatch.setattr(server.changes, "review_nights", lambda: [])
    server.changes_html("щось")
    server.changes_html("")
    assert calls[0] >= 5 * calls[1], "a query must search far beyond the display window"


# --- TC6: rendering --------------------------------------------------------------------------

def test_changes_page_escapes_everything():
    rows = changes.commit_rows("\x1f".join(
        ["c" * 40, "2026-10-31T12:00:00+02:00", '<img src=x onerror="bad()">', "Я"]))
    html = render.render_changes(rows, {}, [], [], 1,
                                 [{"ts": "2026-10-31T10:00:00", "kind": "bash",
                                   "target": "rm", "detail": "<script>bad()</script>"}])
    assert "<img src=x" not in html and "<script>bad()" not in html
    assert "&lt;img src=x" in html


def test_rendering_changes_does_not_grow_sys_path(monkeypatch):
    """t1067: the panel runs 24/7 — one leaked path entry per request never shrinks."""
    import server
    monkeypatch.setattr(server.data, "recent_changes", lambda n: [])
    monkeypatch.setattr(server.changes, "git", lambda *a: "")
    monkeypatch.setattr(server.changes, "ahead_hashes", lambda: set())
    monkeypatch.setattr(server.changes, "review_nights", lambda: [])
    server.changes_html("")
    before = list(sys.path)
    server.changes_html("")
    server.changes_html("")
    # Identical, not merely same length: the handler must add nothing on repeat requests.
    # (Other modules — conftest, status/remind.py — insert the tasks dir on import, so the
    # absolute count is not this code's to assert.)
    assert sys.path == before


def test_changes_page_names_the_missing_review():
    rows = changes.commit_rows(LOG)
    html = render.render_changes(rows, {rows[0]["sha"]: {"task_title": "", "spec": None,
                                                         "tests": [], "review": None}},
                                 [], [], 2, [])
    assert "не записано" in html
    assert "без задачі" in html or "немає задачі" in html


# --- t1110: the Changes screen told three untruths (full review: truth H1, H3, M8) -------

NIGHTLY = """# Ревʼю 2026-11-01

**Вердикт:** 0 High, 2 Medium, 3 Low. Оглянуто 36 комітів.

## High

Нічого.

## Medium

1. **panel/server.py:417 — клікджекінг: жодного X-Frame-Options.**
   Деталі.
2. **memory/facts.py:83 — set_pin пише невалідований рівень.**

## Low

3. **panel/server.py:532 — POST /zirka без Post/Redirect/Get.**
4. **tasks/store.py:106 — номер версії зʼїдається як дедлайн.**
5. **panel/render.py:648 — сортувальні лінки гублять запит.**
"""


def test_a_numbered_nightly_report_is_parsed_not_read_as_zero():
    """The panel-phase scans use `###` headings; the actual nightly review writes numbered
    list items. The screen reported «high: 0, medium: 0, low: 0» for a night that found
    five, and `parsed` was True, so nothing said it had not understood the file."""
    got = changes.findings(NIGHTLY)
    assert len(got.get("medium", [])) == 2 and len(got.get("low", [])) == 3
    assert "клікджекінг" in got["medium"][0]


def test_a_report_in_neither_shape_is_not_counted_as_clean():
    assert changes.findings("# Якийсь текст\n\nбез заголовків\n") == {}
    assert changes.verdict_counts("# Якийсь текст") == {}


def test_the_verdict_line_is_the_fallback_when_nothing_parses():
    assert changes.verdict_counts(NIGHTLY) == {"high": 0, "medium": 2, "low": 3}


def test_a_nights_counts_come_from_the_report_not_from_silence(tmp_path):
    (tmp_path / "2026-11-01-scan.md").write_text(NIGHTLY, encoding="utf-8")
    night = changes.review_nights(tmp_path)[0]
    assert night["parsed"] and night["counts"] == {"high": 0, "medium": 2, "low": 3}


def test_an_unparsable_report_says_so_rather_than_showing_zeros(tmp_path):
    (tmp_path / "2026-11-02-scan.md").write_text("нічого схожого на звіт", encoding="utf-8")
    night = changes.review_nights(tmp_path)[0]
    assert not night["parsed"] and not any(night["counts"].values())


def test_the_lows_of_a_numbered_report_reach_the_backlog(tmp_path):
    (tmp_path / "2026-11-01-scan.md").write_text(NIGHTLY, encoding="utf-8")
    lows = changes.open_lows(changes.review_nights(tmp_path))
    assert len(lows) == 3


def test_a_low_that_was_fixed_is_not_shown_as_open(tmp_path):
    (tmp_path / "2026-11-01-scan.md").write_text(NIGHTLY, encoding="utf-8")
    (tmp_path / "2026-11-01-fixes.md").write_text(
        "# Виправлення\n\nПолагоджено: **panel/server.py:532 — POST /zirka без "
        "Post/Redirect/Get.** (t1099)\n", encoding="utf-8")
    lows = changes.open_lows(changes.review_nights(tmp_path))
    assert all("/zirka" not in low["title"] for low in lows), \
        "«Накопичені Low» is the open backlog, not a list of everything ever raised"
    assert len(lows) == 2


# --- H1: the commit reading is found under either spelling of the sha --------------------

def test_the_reading_is_found_under_the_short_sha(tmp_path, monkeypatch):
    """25 of 39 readings on disk are named with the 7-character sha, including every panel
    commit of today — and the screen said «не записано» about all of them, which is the one
    claim on this page a reader acts on."""
    monkeypatch.setattr(changes, "COMMIT_REVIEW", tmp_path)
    monkeypatch.setattr(changes, "SPECS", tmp_path / "specs")
    monkeypatch.setattr(changes, "TESTS", tmp_path / "tests")
    sha = "9006f16" + "a" * 33
    (tmp_path / "9006f16.md").write_text("# читання", encoding="utf-8")
    got = changes.commit_detail({"sha": sha, "task": "t1103"}, {})
    assert got["review"] and "читання" in got["review"]


def test_the_reading_is_still_found_under_the_full_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(changes, "COMMIT_REVIEW", tmp_path)
    monkeypatch.setattr(changes, "SPECS", tmp_path / "specs")
    monkeypatch.setattr(changes, "TESTS", tmp_path / "tests")
    sha = "b" * 40
    (tmp_path / f"{sha}.md").write_text("# повне", encoding="utf-8")
    assert "повне" in changes.commit_detail({"sha": sha, "task": None}, {})["review"]


def test_a_commit_with_no_reading_still_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(changes, "COMMIT_REVIEW", tmp_path)
    monkeypatch.setattr(changes, "SPECS", tmp_path / "specs")
    monkeypatch.setattr(changes, "TESTS", tmp_path / "tests")
    assert changes.commit_detail({"sha": "c" * 40, "task": None}, {})["review"] is None
