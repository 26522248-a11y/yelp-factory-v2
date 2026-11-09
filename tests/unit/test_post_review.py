"""Post-review warm mode: ladder budget, gate, and a review-free runner (spec section 5)."""

from __future__ import annotations

import pytest

from core.post_review import (
    POST_REVIEW_BUDGET,
    REVIEW_KINDS,
    ladder_plan,
    unlocked_phases,
)
from flows.post_review_warm import PostReviewWarmRunner
from selector_registry.resolver import SelectorRegistry, SelectorRule
from tests.fakes import FakePage

pytestmark = pytest.mark.asyncio

REGISTRY = SelectorRegistry(
    {
        "warmup.search": [SelectorRule("css", "input[name='find_desc']", 1)],
        "warmup.save_business": [SelectorRule("css", "button[aria-label*='Save']", 1)],
        "warmup.vote_useful": [SelectorRule("css", "button[aria-label*='Useful']", 1)],
        "warmup.vote_funny": [SelectorRule("css", "button[aria-label*='Funny']", 1)],
        "warmup.vote_cool": [SelectorRule("css", "button[aria-label*='Cool']", 1)],
        "warmup.follow": [SelectorRule("css", "button:has-text('Follow')", 1)],
        "warmup.friend": [SelectorRule("css", "button:has-text('Add friend')", 1)],
        "warmup.photo_tab": [SelectorRule("css", "a[href*='/photos']", 1)],
        "warmup.checkin": [SelectorRule("css", "button:has-text('Check-in')", 1)],
    }
)


@pytest.fixture(autouse=True)
def _no_photo_network(monkeypatch):
    """Unit tests must never download photos from loremflickr."""
    import core.photo_pool as pool

    monkeypatch.setattr(pool, "pick_photo", lambda *a, **k: None)
    monkeypatch.setattr(pool, "pick_avatar", lambda *a, **k: None)


def test_ladder_is_p0_to_p4_without_review():
    plan = ladder_plan()
    assert [phase for phase, _ in plan] == ["P0", "P1", "P2", "P4"]
    for _, budget in plan:
        assert REVIEW_KINDS.isdisjoint(budget.keys())
        assert "review" not in budget
    # every block budget stays inside the factory table
    table = dict(POST_REVIEW_BUDGET)
    for phase, budget in plan:
        for kind, count in budget.items():
            assert count <= table[phase][kind]


def test_ladder_resumes_at_saved_block_E75():
    assert [phase for phase, _ in ladder_plan("P2")] == ["P2", "P4"]
    assert [phase for phase, _ in ladder_plan("P4")] == ["P4"]
    assert [phase for phase, _ in ladder_plan(None)] == ["P0", "P1", "P2", "P4"]


def test_gate_by_session_count():
    from core.post_review import unlocked_phases_by_session

    assert unlocked_phases_by_session(0) == {"P0"}
    assert unlocked_phases_by_session(1) == {"P0", "P1"}
    assert unlocked_phases_by_session(2) == {"P0", "P1"}
    assert unlocked_phases_by_session(3) == {"P0", "P1", "P2"}
    assert unlocked_phases_by_session(5) == {"P0", "P1", "P2", "P4"}


def test_photo_allowance_resolves_budget_conflict_B4():
    from flows.post_review_warm import PostReviewWarmRunner

    assert PostReviewWarmRunner.photo_allowance(0, 3, 1) == 3
    assert PostReviewWarmRunner.photo_allowance(2, 3, 1) == 3
    assert PostReviewWarmRunner.photo_allowance(3, 3, 1) == 1
    assert PostReviewWarmRunner.photo_allowance(10, 3, 1) == 1


def _runner(settings):
    settings.post_review.rest_between_actions_s = (0, 0)
    settings.post_review.idle_probability = 0.0
    return PostReviewWarmRunner(registry=REGISTRY, settings=settings)


def _wired_page() -> FakePage:
    page = FakePage(url="https://www.yelp.com/search?find_desc=coffee")
    page.add("input[name='find_desc']", visible=True)
    page.add("button[aria-label*='Save']", visible=True)
    page.add("button[aria-label*='Useful']", visible=True)
    page.add("button[aria-label*='Funny']", visible=True)
    page.add("button[aria-label*='Cool']", visible=True)
    page.add("button:has-text('Follow')", visible=True)
    page.add("a[href*='/photos']", visible=True)
    page.add("button:has-text('Check-in')", visible=True)
    return page


async def test_runner_walks_ladder_without_review(settings):
    runner = _runner(settings)
    page = _wired_page()
    outcome = await runner.run_session(page, account_id=None, max_seconds=3600)

    assert outcome["mode"] == "post_review"
    assert outcome["actions"], "session must run actions"
    assert REVIEW_KINDS.isdisjoint(outcome["actions"])
    kinds = set(outcome["actions"])
    assert "pageview" in kinds or "search" in kinds or "scroll" in kinds
    assert outcome["resume_phase"] is None  # ladder finished
    assert not outcome["rate_limited"]


async def test_time_cap_zero_saves_resume_E75(settings):
    runner = _runner(settings)
    page = _wired_page()
    outcome = await runner.run_session(page, account_id=None, max_seconds=0)
    assert outcome["actions"] == []
    assert outcome["resume_phase"] == "P0"


async def test_actions_never_touch_review_selectors(settings):
    runner = _runner(settings)
    page = _wired_page()
    await runner.run_session(page, account_id=None, max_seconds=3600)
    used = {event[1] for event in page.events if event[0] in {"fill", "click", "type"}}
    assert all("review" not in str(selector) for selector in used)
