"""E-93: trust is reachable - 7 days of valid behaviour (+profile complete) >= 75.

This proves the review gate is not a deadlock (B3). The formula is documented in
docs/USER_GUIDE.md ("Công thức trust").
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.assignments import TRUST_REVIEW_THRESHOLD
from core.trust import compute_trust
from db.models import Account, ActionLog, TrustScore, WarmingSession
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready")


def _seed_history(account_id: uuid.UUID, days: int = 7, *, profile_complete: bool = True) -> None:
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        account = session.get(Account, account_id)
        account.created_at = now - timedelta(days=14)
        account.address_line = "1 Test Street"
        account.profile_complete = profile_complete
        for day in range(days):
            started = now - timedelta(days=day, hours=1)
            session.add(
                WarmingSession(
                    account_id=account_id,
                    mode="warm",
                    started_at=started,
                    ended_at=started + timedelta(minutes=40),
                    actions=20,
                    entry_path="search",
                    meta={},
                )
            )
            for kind in ("search", "pageview", "scroll", "save", "vote", "photo", "upload_photo", "follow"):
                session.add(
                    ActionLog(
                        account_id=account_id,
                        kind=kind,
                        target=f"https://www.yelp.com/biz/test-{day}-{kind}",
                        ts=started + timedelta(minutes=kind.__len__()),
                        meta={"proxy_ip": "203.0.113.10", "mode": "warm"},
                    )
                )


def test_seven_days_with_profile_complete_reach_75(make_account):
    account = make_account()
    _seed_history(account.id, days=7, profile_complete=True)
    score = compute_trust(account.id).score
    assert score >= TRUST_REVIEW_THRESHOLD, f"7 days + profile should reach 75, got {score}"


def test_seven_days_without_profile_stay_below_75(make_account):
    account = make_account()
    _seed_history(account.id, days=7, profile_complete=False)
    score = compute_trust(account.id).score
    assert score < TRUST_REVIEW_THRESHOLD, f"incomplete profile must not open the gate, got {score}"


def test_seeded_trust_rows_do_not_affect_the_derived_score(make_account):
    account = make_account()
    with session_scope() as session:
        session.add(TrustScore(account_id=account.id, score=99, components={"fake": True}))
    assert compute_trust(account.id).score < TRUST_REVIEW_THRESHOLD
