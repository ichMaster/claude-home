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

RECALCED = RESUMED + """\

===== 2026-11-02 =====

--- факти ---
t1 транзитний Плутон квадратура натальна Венера

--- письмо ---
ДЕНЬ
Перерахований день.

ПРОГНОЗ
увечері | ясність | стане видно, що головне

ДУГА
Лінія та сама.

--- біоритми ---
ПОКАЗНИКИ: фізичний 11%
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


def test_final_reading_takes_the_newest_run_not_the_loudest_name(monkeypatch, tmp_path):
    """t1148 — full run, --resume, then a full recalc (the panel's «Перерахунок»): the
    recalc's «письмо» was sent last, so a stale «письмо (перероблено)» must not outrank it —
    calibration and reference learning would compare against a reading he never received."""
    _with_log(monkeypatch, tmp_path, RECALCED)
    got = mood.final_reading(date(2026, 11, 2))
    assert "Перерахований день" in got, got
    assert "Перероблений день" not in got


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


# --- t1230: since the v2 cutover the reading lives in astro2's log ----------------------

V1_BIO_ONLY = """\
===== 2026-11-20 =====

--- біоритми ---
ПОКАЗНИКИ: фізичний 12%
"""

V2_LOG = """\
===== 2026-11-20 =====

--- read ---
позиції дня

--- pick ---
голосне

--- wide ---
період

--- day ---
ДЕНЬ
День, який тисне з ранку.

ОСНОВА
w1 Сатурн.
"""

V2_RECALCED = V2_LOG + """\

===== 2026-11-20 =====

--- day ---
ДЕНЬ
Перечитаний день.
"""


def _with_both(monkeypatch, tmp_path, v1_text, v2_text):
    v1 = tmp_path / "mood.log"
    v1.write_text(v1_text, encoding="utf-8")
    v2 = tmp_path / "mood-v2.log"
    v2.write_text(v2_text, encoding="utf-8")
    monkeypatch.setattr(mood, "state_path", lambda key: v1)
    monkeypatch.setattr(mood, "v2_log_path", lambda: v2)


def test_final_reading_finds_the_v2_reading(monkeypatch, tmp_path):
    """t1230 TC1: a post-cutover day lives in astro2's log — learn and calibrate must
    see it, not «нашого читання немає»."""
    _with_both(monkeypatch, tmp_path, V1_BIO_ONLY, V2_LOG)
    got = mood.final_reading(date(2026, 11, 20))
    assert "тисне з ранку" in got
    assert "позиції дня" not in got, "only the day section is the reading"


def test_final_reading_still_reads_a_v1_day(monkeypatch, tmp_path):
    """t1230 TC2: a pre-cutover day stays readable from v1's log."""
    _with_both(monkeypatch, tmp_path, NEW_LOG, V2_LOG)
    got = mood.final_reading(date(2026, 11, 2))
    assert "тяга до теплого" in got


def test_final_reading_takes_the_newest_v2_block(monkeypatch, tmp_path):
    """t1230 TC3: a recalc appends a new block — recency per block, like v1 (t1148)."""
    _with_both(monkeypatch, tmp_path, V1_BIO_ONLY, V2_RECALCED)
    got = mood.final_reading(date(2026, 11, 20))
    assert "Перечитаний день" in got
