"""Smoke tests: the modules import and the config loads. Proves the harness works; real
regression tests live beside their fix in their own test_<area>.py.
"""


def test_config_loads():
    from noosconf import conf
    assert conf("probes.loe.queue", "x") is not None


def test_parse_due_known_phrase():
    import store
    due, _ = store.parse_due("завтра")
    assert due is not None


def test_parse_period_weekend():
    import store
    period, _ = store.parse_period("на вихідних")
    assert period is not None
