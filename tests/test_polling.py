"""Polling cadence + static badge refetch decisions (§4 coordinator table)."""

from conftest import load_fixture

from hockey_score import polling


def test_team_interval_is_live_aware():
    assert polling.next_interval_seconds(True) == 2
    assert polling.next_interval_seconds(False) == 60


def test_static_fetches_on_first_update():
    key = polling.badge_key(load_fixture("idle_vik_ot"))
    assert polling.should_fetch_static(None, key, None, now=0.0) is True


def test_static_waits_for_ttl_when_nothing_changed():
    key = polling.badge_key(load_fixture("idle_vik_ot"))
    assert polling.should_fetch_static(key, key, 0.0, now=899.0) is False
    assert polling.should_fetch_static(key, key, 0.0, now=900.0) is True


def test_static_refetches_immediately_on_fixture_rollover():
    before = polling.badge_key(load_fixture("idle_vik_ot"))
    after = polling.badge_key(load_fixture("idle_after_rollover"))
    assert before != after
    assert polling.should_fetch_static(before, after, 0.0, now=5.0) is True


def test_standings_fetches_on_first_update_then_hourly():
    assert polling.should_fetch_standings(None, now=0.0) is True  # first ever
    assert polling.should_fetch_standings(0.0, now=3599.0) is False  # in TTL
    assert polling.should_fetch_standings(0.0, now=3600.0) is True  # at hour
