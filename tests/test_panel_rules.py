"""t1090 — admin panel, phase 8: the Rules screen, read-only.

The screen shows the four things that govern this assistant and that are invisible without
a terminal: the merged configuration, what actually constrains the session, the systemd
schedule, and which keys exist. It writes nothing — so the tests that matter most are the
ones about what must never reach the page: a personal value, a secret, or a form.
"""
import json
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))

import render                                                           # noqa: E402
import rules_screen                                                     # noqa: E402
import server                                                           # noqa: E402


# --- TC1: defaults against overrides ----------------------------------------------------

DEFAULT = {"probes": {"loe": {"queue": "4.1", "ttl": 600}},
           "panel": {"port": 8091}}
LOCAL = {"probes": {"loe": {"queue": "3.2"}}, "user": {"name": "хтось"}}


def rows_by_key(rows):
    return {r["key"]: r for r in rows}


def test_an_overridden_key_shows_both_values():
    rows = rows_by_key(rules_screen.setting_rows(DEFAULT, LOCAL, []))
    r = rows["probes.loe.queue"]
    assert r["overridden"] and r["value"] == "3.2" and r["default"] == "4.1"


def test_a_default_only_key_is_not_marked_overridden():
    rows = rows_by_key(rules_screen.setting_rows(DEFAULT, LOCAL, []))
    r = rows["probes.loe.ttl"]
    assert not r["overridden"] and r["value"] == "600" and not r["local_only"]


def test_a_local_only_key_says_it_has_no_default():
    rows = rows_by_key(rules_screen.setting_rows(DEFAULT, LOCAL, []))
    r = rows["user.name"]
    assert r["local_only"] and r["default"] == ""


# --- TC2: masked values ------------------------------------------------------------------

def test_a_masked_value_never_reaches_the_row():
    local = {"astro": {"birth": {"place": "Львів", "lat": 12.34}},
             "tasks": {"calendar": {"id": "secret@group.calendar.google.com"}}}
    rows = rows_by_key(rules_screen.setting_rows({}, local,
                                                 ["astro.birth", "tasks.calendar.id"]))
    for key in ("astro.birth.place", "astro.birth.lat", "tasks.calendar.id"):
        assert rows[key]["hidden"], key
        assert rows[key]["value"] == rules_screen.MASK_TEXT


def test_a_masked_value_never_reaches_the_html():
    """The panel listens on the tailnet with no login. Birth data and the calendar id are
    the owner's, not the panel's, and a page is a place things get copied from."""
    local = {"astro": {"birth": {"place": "Львів"}, "context": "ціле життя одним рядком"},
             "voice": {"voices": {"noos": "abc123voiceid"}}}
    rows = rules_screen.setting_rows({}, local,
                                     ["astro.birth", "astro.context", "voice.voices"])
    html = render.render_rules(rows, rules_screen.permissions("", [], {}), [], [], "", "")
    for leak in ("Львів", "ціле життя одним рядком", "abc123voiceid"):
        assert leak not in html, leak
    assert rules_screen.MASK_TEXT in html


def test_masking_matches_a_prefix_not_a_substring():
    assert rules_screen.is_masked("astro.birth.lat", ["astro.birth"])
    assert rules_screen.is_masked("astro.subjects.kira.birth.place", ["astro.subjects"])
    assert not rules_screen.is_masked("astro.birthday_note", ["astro.birth"])
    assert not rules_screen.is_masked("panel.port", ["astro.birth"])


# --- TC3: collections and long strings ---------------------------------------------------

def test_a_list_renders_as_its_length():
    rows = rows_by_key(rules_screen.setting_rows(
        {}, {"probes": {"youtube": {"channels": [{"name": f"c{i}"} for i in range(603)]}}},
        []))
    assert rows["probes.youtube.channels"]["value"] == "список, 603 елементи"


def test_a_long_string_is_truncated():
    rows = rows_by_key(rules_screen.setting_rows({}, {"a": {"b": "я" * 300}}, []))
    assert len(rows["a.b"]["value"]) < 120 and rows["a.b"]["value"].endswith("…")


def test_booleans_and_none_read_in_ukrainian():
    rows = rows_by_key(rules_screen.setting_rows({}, {"a": True, "b": False, "c": None}, []))
    assert rows["a"]["value"] == "так" and rows["b"]["value"] == "ні"
    assert rows["c"]["value"] == "—"


# --- TC4: the schedule -------------------------------------------------------------------

DIGEST_TIMER = """Unit=noos-digest.service
TimersCalendar={ OnCalendar=*-*-* 20:03:00 ; next_elapse=Sun 2026-11-01 20:03:00 EET }
TimersCalendar={ OnCalendar=*-*-* 08:03:00 ; next_elapse=Sun 2026-11-01 08:03:00 EET }
NextElapseUSecRealtime=Sun 2026-11-01 08:03:00 EET
LastTriggerUSec=Sat 2026-10-31 20:03:00 EET
Persistent=yes
Description=Ноос: дайджест зранку і ввечері
ActiveState=active
"""
DIGEST_SERVICE = """Result=success
ExecMainStatus=0
ExecStart={ path=/home/ich/claude-home/status/digest-headless.sh ; argv[]=/home/ich/claude-home/status/digest-headless.sh вечірній ; ignore_errors=no }
Description=Ноос: повний дайджест
ActiveState=inactive
"""


def test_both_schedules_of_a_twice_daily_timer_are_shown():
    row = rules_screen.schedule_rows(
        [("noos-digest.timer", DIGEST_TIMER, DIGEST_SERVICE)])[0]
    assert row["schedules"] == ["*-*-* 08:03:00", "*-*-* 20:03:00"]
    assert row["persistent"] and row["description"] == "Ноос: дайджест зранку і ввечері"


def test_the_command_the_timer_actually_runs_is_shown():
    row = rules_screen.schedule_rows(
        [("noos-digest.timer", DIGEST_TIMER, DIGEST_SERVICE)])[0]
    assert row["command"].endswith("status/digest-headless.sh вечірній")


def test_a_timer_that_never_ran_says_so():
    row = rules_screen.schedule_rows(
        [("noos-x.timer", "LastTriggerUSec=n/a\nActiveState=active\n", "")])[0]
    assert row["last"] == "не запускався" and not row["failed"]


def test_a_failed_service_is_marked_with_its_result():
    row = rules_screen.schedule_rows(
        [("noos-x.timer", "LastTriggerUSec=Sat 2026-10-31 20:03:00 EET\n",
          "Result=exit-code\nExecMainStatus=2\n")])[0]
    assert row["failed"] and row["result"] == "exit-code" and row["exit"] == "2"


def test_unreadable_properties_give_a_row_not_an_exception():
    row = rules_screen.schedule_rows([("noos-x.timer", "", "")])[0]
    assert row["unit"] == "noos-x.timer" and row["schedules"] == []


# --- TC5: keys ---------------------------------------------------------------------------

def test_a_present_key_file_shows_names_and_never_values(tmp_path):
    f = tmp_path / ".env.voice"
    f.write_text("ELEVENLABS_API_KEY=sk-super-secret\n# comment\nEMPTY=\n",
                 encoding="utf-8")
    f.chmod(0o600)
    rows = rules_screen.key_rows(
        [{"file": ".env.voice", "what": "голос", "example": ".env.voice.example"}],
        tmp_path)
    r = rows[0]
    assert r["present"] and r["mode"] == "600"
    assert [(v["name"], v["set"]) for v in r["vars"]] == \
        [("ELEVENLABS_API_KEY", True), ("EMPTY", False)]
    assert "sk-super-secret" not in json.dumps(rows, ensure_ascii=False)


def test_a_missing_key_file_says_so_and_names_its_example(tmp_path):
    (tmp_path / ".env.gmail.example").write_text("GMAIL_USER=\n", encoding="utf-8")
    r = rules_screen.key_rows(
        [{"file": ".env.gmail", "what": "пошта", "example": ".env.gmail.example"}],
        tmp_path)[0]
    assert not r["present"] and r["example_present"] and r["vars"] == []


def test_a_world_readable_key_file_is_flagged(tmp_path):
    f = tmp_path / ".env.news"
    f.write_text("NEWS_KEY=x\n", encoding="utf-8")
    f.chmod(0o644)
    r = rules_screen.key_rows([{"file": ".env.news", "what": "новини"}], tmp_path)[0]
    assert r["loose"], "a key file readable by other users must be visible as a problem"


def test_no_secret_reaches_the_rendered_page(tmp_path):
    f = tmp_path / ".env.voice"
    f.write_text("ELEVENLABS_API_KEY=sk-super-secret\n", encoding="utf-8")
    rows = rules_screen.key_rows([{"file": ".env.voice", "what": "голос"}], tmp_path)
    html = render.render_rules([], rules_screen.permissions("", [], {}), [], rows, "", "")
    assert "sk-super-secret" not in html and "ELEVENLABS_API_KEY" in html


# --- TC6: the standing rules stay honest -------------------------------------------------

def test_every_standing_rule_still_exists_in_the_file_it_cites():
    """The screen states rules in its own words; the words they stand on live in the repo.
    A rule dropped from CLAUDE.md must break this test, not keep being displayed."""
    for r in rules_screen.standing_rules():
        source = ROOT / r["source"]
        assert source.is_file(), r["source"]
        text = source.read_text(encoding="utf-8")
        assert r["anchor"] in text, f"{r['source']} no longer says: {r['anchor']}"


def test_permission_mode_comes_from_the_file_that_sets_it():
    mode = rules_screen.permission_mode(
        'BASE_ARGS=(--remote-control "home" --permission-mode auto)')
    assert mode == "auto"
    assert rules_screen.permission_mode("no flags here") == "невідомо"


def test_no_allowlist_is_reported_as_absent_not_as_empty_safety():
    """There is no allow/deny list on this machine. Showing «0 правил» would read as
    «нічого не дозволено», which is the opposite of the truth."""
    p = rules_screen.permissions("--permission-mode auto", [], {})
    assert p["mode"] == "auto" and p["lists"] == []
    html = render.render_rules([], p, [], [], "", "")
    assert "списків дозволів немає" in html


def test_a_configured_allowlist_is_listed_with_its_file():
    p = rules_screen.permissions(
        "--permission-mode default",
        [("~/.claude/settings.json",
          {"permissions": {"allow": ["Bash(git:*)"], "deny": ["Read(./.env*)"]}})], {})
    assert p["lists"][0]["file"].endswith("settings.json")
    assert p["lists"][0]["allow"] == ["Bash(git:*)"]
    assert p["lists"][0]["deny"] == ["Read(./.env*)"]


def test_the_bot_limits_are_shown_because_they_are_a_permission():
    p = rules_screen.permissions("", [], {"max_per_hour": 20})
    assert p["inbox"]["max_per_hour"] == 20
    html = render.render_rules([], p, [], [], "", "")
    assert "20" in html


# --- TC7: the screen --------------------------------------------------------------------

def test_the_screen_has_its_four_sections():
    html = render.render_rules([], rules_screen.permissions("", [], {}), [], [], "", "")
    for heading in ("Налаштування", "Дозволи", "Розклад", "Ключі"):
        assert f"<h2>{heading}" in html or f">{heading}<" in html, heading
    assert "фаза 8" not in html


def test_rules_is_no_longer_a_placeholder():
    assert "/rules" not in server.SOON


def test_the_screen_carries_no_form_because_the_phase_only_reads():
    """Phase 8 reads. Editing is phase 10, after the panel has authentication (the owner,
    2026-11-01) — until then a form here would write as `ich` with nobody's signature."""
    html = render.render_rules(
        rules_screen.setting_rows(DEFAULT, LOCAL, []),
        rules_screen.permissions("--permission-mode auto", [], {"max_per_hour": 20}),
        rules_screen.schedule_rows([("noos-digest.timer", DIGEST_TIMER, DIGEST_SERVICE)]),
        rules_screen.key_rows([{"file": ".env.voice", "what": "голос"}], ROOT),
        "", "")
    assert 'method="post"' not in html


def test_the_values_are_escaped():
    rows = rules_screen.setting_rows({}, {"a": {"b": "<script>x</script>"}}, [])
    html = render.render_rules(rows, rules_screen.permissions("", [], {}), [], [], "", "")
    assert "<script>" not in html and "&lt;script&gt;" in html


# --- TC8: read-only, and no unit name from a query string reaches a command --------------

def test_a_journal_is_read_only_for_a_unit_systemd_itself_named(monkeypatch):
    calls = []

    def fake_run(*cmd, **kwargs):
        calls.append(cmd)
        return True, "два рядки журналу"
    monkeypatch.setattr(server, "run_script", fake_run)
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-digest.timer"])

    said = server.journal_text("noos-digest.service")
    assert "журналу" in said and calls and "journalctl" in calls[0][0]


def test_an_unknown_unit_never_reaches_journalctl(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "run_script",
                        lambda *cmd, **kw: (calls.append(cmd), (True, ""))[1])
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-digest.timer"])

    for attack in ("ssh-agent.service", "noos-digest.timer; rm -rf ~",
                   "../../etc/passwd", "-u", ""):
        said = server.journal_text(attack)
        assert "не знаю" in said.lower() or "невідом" in said.lower(), attack
    assert calls == [], "a unit name from a query string must never be executed"


def test_an_interval_timer_shows_its_interval_not_a_dash():
    """Four timers run on an interval and carry no OnCalendar at all — the watcher, the
    bots, the reminders, the indexer. A «—» there reads as «розкладу немає»."""
    row = rules_screen.schedule_rows([(
        "claude-memory.timer",
        "TimersMonotonic={ OnUnitActiveUSec=15min ; next_elapse=4w 1d }\n"
        "TimersMonotonic={ OnBootUSec=5min ; next_elapse=5min }\n"
        "ActiveState=active\n", "")])[0]
    assert row["schedules"] == ["кожні 15 хв після завершення",
                               "через 5 хв після старту системи"]


# --- t1094 (H1): the journal pane published the unit's own output on an open port -------
# The settings table on this very page masks `user.name` because the port is unauthenticated.
# The pane beside it printed the digest's calendar block. Only systemd's own lines are shown
# now; a unit's stdout waits for the phase that brings authentication.

def journal_calls(monkeypatch, scope="systemd"):
    calls = []

    def fake_run(*cmd, **kwargs):
        calls.append(cmd)
        return True, "Finished Ноос: повний дайджест."
    monkeypatch.setattr(server, "run_script", fake_run)
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-digest.timer"])
    real = server.conf
    monkeypatch.setattr(server, "conf",
                        lambda key, default=None: scope if key == "panel.journal_scope"
                        else real(key, default))
    return calls


def test_the_journal_pane_asks_only_for_systemd_s_own_lines(monkeypatch):
    calls = journal_calls(monkeypatch)
    server.journal_text("noos-digest.service")
    assert calls and "-t" in calls[0] and "systemd" in calls[0], calls


def test_the_full_journal_is_a_config_decision_not_a_code_change(monkeypatch):
    calls = journal_calls(monkeypatch, scope="full")
    server.journal_text("noos-digest.service")
    assert "-t" not in calls[0], calls


def test_the_pane_says_what_it_withholds_and_how_to_see_it():
    html = render.render_rules([], rules_screen.permissions("", [], {}), [],
                               [], "Finished.", "noos-digest.service", filtered=True)
    assert "journalctl --user -u noos-digest.service" in html
    assert "приховано" in html
    full = render.render_rules([], rules_screen.permissions("", [], {}), [],
                               [], "Finished.", "noos-digest.service", filtered=False)
    assert "приховано" not in full.split("<h2>Розклад")[1]


# --- t1095 (M2): the interval timers were never asked about ------------------------------
# The parser landed in t1090 and the property was never requested, so the four timers that
# run most often said «—» — which reads as "no schedule", not as "unknown".

def test_rules_html_asks_systemd_about_interval_timers(monkeypatch):
    asked = []

    def fake_show(unit, properties):
        asked.append(properties)
        return ""
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-watch.timer"])
    monkeypatch.setattr(server.data, "show", fake_show)
    server.rules_html()
    timer_props = asked[0]
    assert "TimersMonotonic" in timer_props and "NextElapseUSecMonotonic" in timer_props


@pytest.mark.parametrize("text,seconds", [
    ("4w 1d 13h 23min 5.346337s", 4 * 604800 + 86400 + 13 * 3600 + 23 * 60 + 5.346337),
    ("15min", 900.0),
    ("2min 30s", 150.0),
    ("500ms", 0.5),
    ("1h", 3600.0),
])
def test_parse_span_reads_systemd_s_duration_spelling(text, seconds):
    assert abs(rules_screen.parse_span(text) - seconds) < 0.001


@pytest.mark.parametrize("text", ["", "n/a", "скоро", "4 тижні"])
def test_parse_span_refuses_nonsense(text):
    assert rules_screen.parse_span(text) is None


def test_an_interval_timer_gets_a_real_next_run_from_the_boot_clock():
    boot = 1762000000.0                      # a fixed epoch: the test owns the clock
    row = rules_screen.schedule_rows([(
        "noos-watch.timer",
        "TimersMonotonic={ OnUnitActiveUSec=15min ; next_elapse=1h }\n"
        "NextElapseUSecMonotonic=1h\nActiveState=active\n", "")], boot_epoch=boot)[0]
    import time
    assert row["next"] == time.strftime("%Y-%m-%d %H:%M:%S",
                                        time.localtime(boot + 3600))


def test_without_a_boot_clock_the_next_run_stays_blank_not_wrong():
    row = rules_screen.schedule_rows([(
        "noos-watch.timer", "NextElapseUSecMonotonic=1h\n", "")])[0]
    assert row["next"] == ""


def test_a_calendar_timer_keeps_its_realtime_next_run():
    row = rules_screen.schedule_rows(
        [("noos-digest.timer", DIGEST_TIMER, DIGEST_SERVICE)], boot_epoch=1762000000.0)[0]
    assert row["next"] == "Sun 2026-11-01 08:03:00 EET"


def test_the_doc_no_longer_claims_fifteen_timers():
    doc = (ROOT / "docs/features/ADMIN-PANEL.md").read_text(encoding="utf-8")
    assert "15 systemd user timers" not in doc and "all 15 timers" not in doc


@pytest.mark.parametrize("seconds,text", [
    (900, "15 хв"), (7200, "2 год"), (86400, "1 д"), (30, "30 с"), (0.5, "500 мс"),
    (None, ""),
])
def test_an_interval_reads_as_ukrainian_not_as_systemd_s_abbreviation(seconds, text):
    """This line is listened to as often as it is read — «15min» is Latin and clipped."""
    assert rules_screen.span_text(seconds) == text


# --- t1096 (M3): the journal was cut from the front --------------------------------------

LONG_JOURNAL = "\n".join(f"2026-11-01T0{i // 10}:{i % 10:02d}:00 рядок номер {i}"
                         for i in range(1, 41))


def journal_with(monkeypatch, output, **settings):
    def fake_run(*cmd, timeout=300, cap=600, tail=False):   # mirrors run_script's shape
        said = output
        if cap and len(said) > cap:
            said = ("… обрізано\n" + said[-cap:]) if tail else said[:cap]
        return True, said
    monkeypatch.setattr(server, "run_script", fake_run)
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-digest.timer"])
    real = server.conf
    monkeypatch.setattr(server, "conf",
                        lambda key, default=None: settings.get(key, real(key, default)))


def test_the_journal_pane_shows_the_newest_lines(monkeypatch):
    """«Чому дайджест мовчав» is answered by the end of the journal, not its beginning."""
    journal_with(monkeypatch, LONG_JOURNAL)
    said = server.journal_text("noos-digest.service")
    assert "рядок номер 40" in said


def test_the_journal_is_not_clamped_to_six_hundred_characters(monkeypatch):
    journal_with(monkeypatch, LONG_JOURNAL)
    assert len(server.journal_text("noos-digest.service")) > 600


def test_a_cut_journal_says_it_was_cut(monkeypatch):
    journal_with(monkeypatch, LONG_JOURNAL, **{"panel.journal_chars": 200})
    said = server.journal_text("noos-digest.service")
    assert "обрізано" in said and "рядок номер 40" in said


def test_an_uncut_journal_carries_no_marker(monkeypatch):
    journal_with(monkeypatch, "Finished Ноос: повний дайджест.")
    assert "обрізано" not in server.journal_text("noos-digest.service")


def test_the_line_count_from_config_reaches_the_command(monkeypatch):
    calls = []

    def fake_run(*cmd, timeout=300, cap=600, tail=False):
        calls.append(cmd)
        return True, "ok"
    monkeypatch.setattr(server, "run_script", fake_run)
    monkeypatch.setattr(server.data, "timer_units", lambda: ["noos-digest.timer"])
    real = server.conf
    monkeypatch.setattr(server, "conf",
                        lambda key, default=None: 7 if key == "panel.journal_lines"
                        else real(key, default))
    server.journal_text("noos-digest.service")
    assert "7" in calls[0]


def test_the_other_callers_keep_the_head_clamp():
    """A task message rides a redirect query string, so its 600-character head clamp is the
    right behaviour and must not change with the journal's needs."""
    ok, said = server.run_script("printf", "x" * 2000)
    assert ok and len(said) == 600 and said.startswith("x")


# --- t1097 (M4): a multi-line value became a variable name -------------------------------

PEM_ENV = '''GOOGLE_KEY="-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ==
-----END PRIVATE KEY-----"
'''


def test_a_multiline_value_is_not_mistaken_for_a_name(tmp_path):
    """A base64 line carries `=` as padding, so the key's own body came back as a «name» —
    on the port with no login, in the one section whose promise is "never a value"."""
    (tmp_path / ".env.youtube").write_text(PEM_ENV, encoding="utf-8")
    r = rules_screen.key_rows([{"file": ".env.youtube", "what": "OAuth"}], tmp_path)[0]
    assert [v["name"] for v in r["vars"]] == ["GOOGLE_KEY"]
    html = render.render_rules([], rules_screen.permissions("", [], {}), [], [r], "", "")
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ" not in html


def test_a_multiline_value_counts_as_one_variable_and_no_odd_lines(tmp_path):
    """Its body belongs to the value — it is neither a variable nor junk."""
    (tmp_path / ".env.youtube").write_text(PEM_ENV, encoding="utf-8")
    r = rules_screen.key_rows([{"file": ".env.youtube", "what": "OAuth"}], tmp_path)[0]
    assert r["unparsed"] == 0 and len(r["vars"]) == 1 and r["vars"][0]["set"]


def test_the_lines_it_could_not_read_are_counted_not_hidden(tmp_path):
    (tmp_path / ".env.youtube").write_text(
        "A=1\nцей рядок не змінна\n99BAD=2\n", encoding="utf-8")
    r = rules_screen.key_rows([{"file": ".env.youtube", "what": "OAuth"}], tmp_path)[0]
    assert [v["name"] for v in r["vars"]] == ["A"]
    assert r["unparsed"] == 2
    html = render.render_rules([], rules_screen.permissions("", [], {}), [], [r], "", "")
    assert "не схожі на змінні" in html or "не схожий на змінну" in html


def test_ordinary_env_shapes_still_parse(tmp_path):
    (tmp_path / ".env.voice").write_text(
        "# comment\n\nNAME=value\nexport OTHER=value\nURL=https://x/y?a=b\n",
        encoding="utf-8")
    r = rules_screen.key_rows([{"file": ".env.voice", "what": "голос"}], tmp_path)[0]
    assert [v["name"] for v in r["vars"]] == ["NAME", "OTHER", "URL"]
    assert r["unparsed"] == 0


@pytest.mark.parametrize("line,is_set", [
    ('FOO=""', False), ("FOO=''", False), ("FOO=", False), ("FOO=x", True),
    ('FOO=" "', False),
])
def test_an_explicitly_emptied_variable_reads_as_empty(tmp_path, line, is_set):
    """«Задано» is the claim a reader checks when a probe is warning: it must mean
    configured, and `FOO=""` is not configured."""
    (tmp_path / ".env.voice").write_text(line + "\n", encoding="utf-8")
    r = rules_screen.key_rows([{"file": ".env.voice", "what": "голос"}], tmp_path)[0]
    assert r["vars"][0]["set"] is is_set
