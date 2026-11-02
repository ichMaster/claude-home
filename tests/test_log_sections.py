"""t1127 — the t1126 rename of the mood-log sections left four consumers parsing the old
names: calibration (forecast_of), reference learning (astro_learn.ours), yesterday's context
(yesterday_block) and the panel's Zirka screen. Each test here fabricates a NEW-format log —
the shape every run writes since 2026-11-01 — and asks the consumer to find the reading."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("noos_mood", ROOT / "status" / "mood.py")
mood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mood)

NEW_LOG = """\
===== 2026-11-02 =====

--- факти ---
t1 транзитний Плутон квадратура натальна Венера

--- вибір ---
ДУГА — t1: лінія триває.

--- письмо ---
ДЕНЬ
День, у якому тягне назовні.

ПРОГНОЗ
до обіду | тяга до теплого | написати тому, про кого думаєш, або потягне в самоту

ДІЯ
Не вирішувати нічого про гроші.

ДУГА
Та сама лінія з вересня, це її плато.

ОСНОВА
Плутон квадратура Венера, орбіс 0.2.

--- перевірка ---
ОЦІНКА
все тримається

--- біоритми ---
ПОКАЗНИКИ: фізичний 12%
"""

RESUMED = NEW_LOG + """\

===== 2026-11-02 =====

--- письмо (перероблено) ---
ДЕНЬ
Перероблений день.

ПРОГНОЗ
увечері | втома | захочеться тиші

ДУГА
Лінія та сама.
"""

OLD_LOG = """\
===== 2026-10-30 =====

--- підсумок ---
ПІДСУМОК: старий текст дня.
"""


def _with_log(monkeypatch, tmp_path, text):
    log = tmp_path / "mood.log"
    log.write_text(text, encoding="utf-8")
    monkeypatch.setattr(mood, "state_path", lambda key: log)
    return log


# --- TC1/TC2: the sent reading is found under its current section names ----------------------

def test_final_reading_sees_the_new_format(monkeypatch, tmp_path):
    _with_log(monkeypatch, tmp_path, NEW_LOG)
    got = mood.final_reading(date(2026, 11, 2))
    assert "тяга до теплого" in got
    assert "ОЦІНКА" not in got, "перевірка holds the raw check output, not the reading"


def test_final_reading_prefers_the_resumed_text(monkeypatch, tmp_path):
    _with_log(monkeypatch, tmp_path, RESUMED)
    got = mood.final_reading(date(2026, 11, 2))
    assert "Перероблений день" in got


def test_final_reading_still_reads_the_legacy_format(monkeypatch, tmp_path):
    _with_log(monkeypatch, tmp_path, OLD_LOG)
    assert "старий текст дня" in mood.final_reading(date(2026, 10, 30))


def test_forecast_of_uses_the_same_chain(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / "status"))
    import mood_feedback                                                 # noqa: E402
    import mood as prod_mood                                             # noqa: E402
    log = tmp_path / "mood.log"
    log.write_text(NEW_LOG, encoding="utf-8")
    monkeypatch.setattr(prod_mood, "state_path", lambda key: log)
    got = mood_feedback.forecast_of(date(2026, 11, 2))
    assert "тяга до теплого" in got, "calibrate() exits at «немає прогнозу» without this"


# --- TC3: reference learning ------------------------------------------------------------------

def test_astro_learn_ours_sees_the_new_format(monkeypatch, tmp_path):
    _spec2 = importlib.util.spec_from_file_location(
        "noos_astro_learn", ROOT / "status" / "astro_learn.py")
    learn = importlib.util.module_from_spec(_spec2)
    _spec2.loader.exec_module(learn)
    log = tmp_path / "mood.log"
    log.write_text(RESUMED, encoding="utf-8")
    import mood as prod_mood                                             # noqa: E402
    monkeypatch.setattr(prod_mood, "state_path", lambda key: log)
    got = learn.ours(date(2026, 11, 2))
    assert "Перероблений день" in got, "РОЗХОДЖЕННЯ is silently skipped without this"


# --- TC4: yesterday's context -----------------------------------------------------------------

def test_yesterday_block_sees_a_new_format_reading(monkeypatch, tmp_path):
    _with_log(monkeypatch, tmp_path, NEW_LOG)
    block = mood.yesterday_block(date(2026, 11, 3))
    assert "тяга до теплого" in block
    assert "2026-11-02" in block


def test_yesterday_block_prefers_the_resumed_run(monkeypatch, tmp_path):
    _with_log(monkeypatch, tmp_path, RESUMED)
    block = mood.yesterday_block(date(2026, 11, 3))
    assert "Перероблений день" in block


# --- TC5: the Zirka screen --------------------------------------------------------------------

def test_zirka_finds_the_new_format_summary():
    sys.path.insert(0, str(ROOT / "panel"))
    import zirka                                                         # noqa: E402
    runs = zirka.day_runs(NEW_LOG, "2026-11-02")
    assert runs and "тяга до теплого" in runs[0]["summary"]


def test_zirka_measures_the_new_blocks_against_the_spoken_budget():
    sys.path.insert(0, str(ROOT / "panel"))
    import zirka                                                         # noqa: E402
    summary = ("ДЕНЬ\nКороткий день.\n\nПРОГНОЗ\nдо обіду | тяга | написати\n\n"
               "ДІЯ\nНічого не підписувати.\n\nДУГА\nЛінія та сама.\n\nОСНОВА\nПлутон 0.2.")
    blocks = zirka.reading_blocks(summary)
    names = [b["name"] for b in blocks]
    for want in ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА", "ОСНОВА"):
        assert want in names, f"a new-format reading must be measured, not reported missing"
    assert not any(b["missing"] for b in blocks if b["name"] in
                   ("ДЕНЬ", "ПРОГНОЗ", "ДІЯ", "ДУГА", "ОСНОВА"))


def test_zirka_still_measures_the_legacy_blocks():
    sys.path.insert(0, str(ROOT / "panel"))
    import zirka                                                         # noqa: E402
    blocks = {b["name"]: b for b in zirka.reading_blocks(
        "КОРОТКО: " + "я" * 400 + "\nПІДСУМОК: коротко")}
    assert blocks["КОРОТКО"]["over"] is True and blocks["КОРОТКО"]["budget"] == 300
