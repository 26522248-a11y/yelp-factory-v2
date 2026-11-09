"""E-95: the P0->P4 ladder gate and the daily cap must read *warm* sessions.

Deadlock #2 (found statically on c600b3f): days_active had been opened to mode="warm"
but session_count / sessions_today still filtered mode == "post_review", so an account
warming normally reported 0 sessions -> unlocked_phases_by_session(0) returned {"P0"}
forever, and the daily cap in orchestrator.run_post_review_warm read the same 0.

Counting rule under test is the one fixed for warm evidence in core/trust.py: both
ladders ("warm" + "post_review") count, meta.seed rows never count.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.post_review import (
    days_active,
    mark_reviews_done,
    session_count,
    sessions_today,
    unlocked_phases_by_session,
)
from db.models import WarmingSession
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready")


def _add_session(
    account_id: uuid.UUID,
    *,
    mode: str = "warm",
    days_ago: int = 1,
    actions: int = 20,
    meta: dict | None = None,
) -> None:
    started = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    with session_scope() as session:
        session.add(
            WarmingSession(
                account_id=account_id,
                mode=mode,
                started_at=started,
                ended_at=started + timedelta(minutes=30),
                actions=actions,
                entry_path="ladder",
                meta=meta or {},
            )
        )


def _deps(settings):
    from core.orchestrator import SignupDeps
    from tests.fakes import FakeGPM
    from tests.unit.test_post_review import REGISTRY

    return SignupDeps(settings=settings, gpm=FakeGPM(), registry=REGISTRY, email=None, captcha=None)


def test_warm_only_account_is_not_stuck_on_p0(make_account):
    """5 real warm sessions must unlock the ladder exactly like 5 post_review sessions."""
    account = make_account()
    for day in range(1, 6):
        _add_session(account.id, mode="warm", days_ago=day)

    count = session_count(account.id)
    assert count == 5, f"session_count must see warm-mode sessions, got {count}"

    unlocked = unlocked_phases_by_session(count)
    assert unlocked != {"P0"}, "an account with 5 real sessions must leave P0"
    assert unlocked == {"P0", "P1", "P2", "P4"}, f"unexpected ladder for 5 sessions: {unlocked}"
    assert days_active(account.id) == 5


def test_post_review_only_count_is_unchanged(make_account):
    """The other ladder must keep working - the fix is additive, not a swap."""
    account = make_account()
    _add_session(account.id, mode="post_review", days_ago=1)
    _add_session(account.id, mode="post_review", days_ago=2)
    assert session_count(account.id) == 2
    assert unlocked_phases_by_session(session_count(account.id)) == {"P0", "P1"}


def test_seeded_warm_rows_are_not_real_sessions(make_account):
    """meta.seed is imported history, not work the account did (same rule as warm evidence)."""
    account = make_account()
    _add_session(account.id, mode="warm", days_ago=1, meta={"seed": True})
    _add_session(account.id, mode="warm", days_ago=2, meta={"seed": True})
    _add_session(account.id, mode="warm", days_ago=3)

    assert session_count(account.id) == 1, "seeded rows must not unlock the ladder"


def test_unknown_mode_is_not_counted(make_account):
    """WARM_MODES is an explicit list - a new mode must be added on purpose, never by accident."""
    account = make_account()
    _add_session(account.id, mode="browse", days_ago=1)
    assert session_count(account.id) == 0


async def test_warm_session_today_still_trips_the_daily_cap(settings, make_account):
    """Requested by DUC: cadence must be enforced on warm too, else an account runs 2+/day."""
    from core.orchestrator import run_post_review_warm

    account = make_account()
    mark_reviews_done(account.id)
    _add_session(account.id, mode="warm", days_ago=0)

    assert sessions_today(account.id) == 1, "a warm session started today must count as cadence"

    result = await run_post_review_warm(account.id, _deps(settings))
    assert result.get("status") == "SKIPPED_TODAY", f"warm session today must block a second run: {result}"


@pytest.mark.xfail(
    strict=False,
    reason="days_active still counts meta.seed rows while session_count and warm evidence exclude "
    "them, so imported history alone can satisfy the 7-day hard gate "
    "(core/assignments.py:_profile_ready). Scope decision for MINH, not a flake.",
)
def test_days_active_also_excludes_seed_rows(make_account):
    account = make_account()
    for day in range(1, 9):
        _add_session(account.id, mode="warm", days_ago=day, meta={"seed": True})

    assert session_count(account.id) == 0
    assert days_active(account.id) == 0, f"seeded history must not build the 7-day gate, got {days_active(account.id)}"

