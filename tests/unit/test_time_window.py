"""Metro-local scheduling window (timezone fix, 2026-11-09)."""

from __future__ import annotations

from datetime import datetime, timezone

from core.post_review import within_account_window


def _utc(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_est_window_boundaries():
    # November = EST (UTC-5): 08:00 local == 13:00 UTC, 20:00 local == 01:00 UTC next day
    assert within_account_window("America/New_York", _utc(2026, 11, 9, 13, 0)) is True
    assert within_account_window("America/New_York", _utc(2026, 11, 9, 12, 59)) is False
    assert within_account_window("America/New_York", _utc(2026, 11, 10, 0, 59)) is True
    assert within_account_window("America/New_York", _utc(2026, 11, 10, 1, 1)) is False


def test_pacific_is_three_hours_behind_est():
    # 13:00 UTC = 08:00 EST but 05:00 PST -> outside the window in LA
    assert within_account_window("America/Los_Angeles", _utc(2026, 11, 9, 13, 0)) is False
    assert within_account_window("America/Los_Angeles", _utc(2026, 11, 9, 16, 0)) is True


def test_invalid_timezone_falls_back_to_eastern():
    assert within_account_window("Not/AZone", _utc(2026, 11, 9, 13, 0)) is True


def test_dst_transitions_do_not_shift_the_window():
    # 2026-03-08: DST starts (2am -> 3am, EST->EDT, UTC-5->UTC-4)
    # 08:00 local == 12:00 UTC on that date (after the switch)
    assert within_account_window("America/New_York", _utc(2026, 3, 8, 12, 0)) is True
    assert within_account_window("America/New_York", _utc(2026, 3, 8, 11, 59)) is False
    # 2026-11-01: DST ends (2am -> 1am, EDT->EST, UTC-4->UTC-5)
    # 08:00 local == 13:00 UTC on that date (after the switch)
    assert within_account_window("America/New_York", _utc(2026, 11, 1, 13, 0)) is True
    assert within_account_window("America/New_York", _utc(2026, 11, 1, 12, 59)) is False
