"""Volume governor and lifecycle transitions (2026-11-09 pool model)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import core.volume as volume
from core.state_machine import can_transition
from db.models import AccountState


def test_review_threshold_constant_alignment():
    from core.assignments import TRUST_REVIEW_THRESHOLD
    from core.trust import REVIEW_THRESHOLD

    assert TRUST_REVIEW_THRESHOLD == REVIEW_THRESHOLD == 75


@pytest.mark.parametrize("week,expected", [(1, False), (2, True), (3, False), (4, True), (5, False), (6, True)])
def test_lazy_week_deterministic(week, expected):
    fake = datetime.fromisocalendar(2026, week, 1).replace(tzinfo=timezone.utc)
    assert volume.is_lazy_week(fake) is expected


def test_multiplier_pin_and_pause(monkeypatch):
    monkeypatch.setattr(volume, "get_flag", lambda key, default=None: {"multiplier": 1.5})
    assert volume.effective_multiplier() == 1.5
    monkeypatch.setattr(volume, "get_flag", lambda key, default=None: {"paused": True})
    assert volume.effective_multiplier() == 0.0


def test_lazy_week_multiplier(monkeypatch):
    monkeypatch.setattr(volume, "get_flag", lambda key, default=None: {})
    monkeypatch.setattr(volume, "filter_rate_7d", lambda: 0.0)
    lazy = datetime.fromisocalendar(2026, 2, 1).replace(tzinfo=timezone.utc)
    active = datetime.fromisocalendar(2026, 1, 1).replace(tzinfo=timezone.utc)
    assert volume.effective_multiplier(lazy) == pytest.approx(0.6)
    assert volume.effective_multiplier(active) == pytest.approx(1.0)


def test_filter_throttle_multiplier(monkeypatch):
    monkeypatch.setattr(volume, "get_flag", lambda key, default=None: {})
    monkeypatch.setattr(volume, "filter_rate_7d", lambda: 0.5)
    active = datetime.fromisocalendar(2026, 1, 1).replace(tzinfo=timezone.utc)
    assert volume.effective_multiplier(active) == pytest.approx(0.7)


def test_slot_hour_inside_window():
    import random

    rng = random.Random(9)
    hours = {volume.pick_slot_hour(rng) for _ in range(200)}
    assert all(8 <= hour <= 20 for hour in hours)
    assert hours & set(range(8, 12))  # morning band exists
    assert hours & set(range(12, 18))  # afternoon band exists
    assert hours & set(range(17, 21))  # evening band exists


def test_lifecycle_transitions():
    assert can_transition(AccountState.WARMING, AccountState.READY)
    assert can_transition(AccountState.READY, AccountState.ACTIVE)
    assert can_transition(AccountState.ACTIVE, AccountState.COOLDOWN)
    assert can_transition(AccountState.COOLDOWN, AccountState.WARMING)
    assert can_transition(AccountState.NEEDS_MANUAL, AccountState.ACTIVE)
    assert can_transition(AccountState.BANNED, AccountState.RETIRED)
    # legacy signup chain stays intact
    assert can_transition(AccountState.NEW, AccountState.PROVISIONING)
    assert can_transition(AccountState.SUBMITTED, AccountState.EMAIL_PENDING)
    # retired is terminal
    assert not can_transition(AccountState.RETIRED, AccountState.ACTIVE)


def test_keyword_mix_ratio():
    import random

    from flows.post_review_warm import KEYWORD_MIX, choose_keyword

    rng = random.Random(5)
    picks = [choose_keyword(rng) for _ in range(3000)]
    food_words = set(KEYWORD_MIX[0][2])
    food_share = sum(1 for pick in picks if pick in food_words) / len(picks)
    assert 0.33 <= food_share <= 0.47  # target 40%
    assert len(set(picks)) >= 20  # broad service coverage, not just food
