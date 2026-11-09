"""E-76 / E-80: post-review daily cadence and the reviews_done gate (spec section 5).

Requires Postgres (skipped automatically when unreachable).
"""

from __future__ import annotations

import uuid

import pytest

from core.config import get_settings
from core.orchestrator import SignupDeps, run_post_review_warm
from core.post_review import mark_reviews_done, sessions_today
from db.models import Account, WarmingSession
from db.session import session_scope
from tests.fakes import FakeGPM

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("db_ready")]


def _deps(settings):
    from tests.fakes import FakePage
    from tests.unit.test_post_review import REGISTRY

    return SignupDeps(
        settings=settings,
        gpm=FakeGPM(),
        registry=REGISTRY,
        email=None,
        captcha=None,
    )


async def test_E80_mode_requires_reviews_done(settings, make_account):
    account = make_account()
    result = await run_post_review_warm(account.id, _deps(settings))
    assert result["ok"] is False
    assert result["error_code"] == "not_reviews_done"


async def test_mark_reviews_done_flag(settings, make_account):
    account = make_account()
    assert mark_reviews_done(account.id)["reviews_done"] is True
    with session_scope() as session:
        assert session.get(Account, account.id).reviews_done is True


async def test_E76_second_session_same_day_is_skipped(settings, make_account):
    account = make_account()
    mark_reviews_done(account.id)
    with session_scope() as session:
        session.add(
            WarmingSession(
                account_id=account.id,
                mode="post_review",
                meta={"note": "already ran today"},
            )
        )
    assert sessions_today(account.id) == 1
    result = await run_post_review_warm(account.id, _deps(settings))
    assert result.get("status") == "SKIPPED_TODAY"
