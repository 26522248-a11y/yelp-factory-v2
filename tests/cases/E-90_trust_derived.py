"""E-90: trust is derived - a stored/seeded score cannot open the review gate.

Also proves the DB-level unique (client_id, account_id) that makes re-assigning the
same account to the same business impossible.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from core.assignments import plan_assignments
from core.clients import ensure_metro
from core.trust import compute_trust
from db.models import Account, Assignment, Client, TrustScore
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready")


def test_seeded_trust_is_ignored_by_the_planner(make_account):
    metro = ensure_metro("Test Metro, NY")
    account = make_account()
    with session_scope() as session:
        row = session.get(Account, account.id)
        row.metro_id = metro
        session.add(TrustScore(account_id=account.id, score=95, components={"fake": True}))

    # derived trust ignores action-less history (seeded 95 does not count)
    assert compute_trust(account.id).score < 75

    client_id = uuid.uuid4()
    biz = f"test-biz-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        session.add(
            Client(
                id=client_id,
                business_name="Gate Test Diner",
                metro_id=metro,
                category="restaurants",
                yelp_biz_id=biz,
                facts={"menu": ["eggs"], "price_examples": ["$9"]},
            )
        )
    try:
        created = plan_assignments(limit=5)
        assert all(item["account"] != str(account.id) for item in created)
    finally:
        with session_scope() as session:
            session.query(Assignment).filter(Assignment.client_id == client_id).delete()
            session.query(Client).filter(Client.id == client_id).delete()


def test_unique_account_client_constraint(make_account):
    metro = ensure_metro("Test Metro, NY")
    account = make_account()
    client_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            Client(
                id=client_id,
                business_name="Unique Test Cafe",
                metro_id=metro,
                category="restaurants",
                yelp_biz_id=f"test-unique-{uuid.uuid4().hex[:8]}",
                facts={"menu": ["latte"], "price_examples": ["$5"]},
            )
        )
    with session_scope() as session:
        session.add(Assignment(client_id=client_id, account_id=account.id, status="planned"))

    try:
        with pytest.raises(IntegrityError):
            with session_scope() as session:
                session.add(Assignment(client_id=client_id, account_id=account.id, status="planned"))
                session.flush()
    finally:
        with session_scope() as session:
            session.query(Assignment).filter(Assignment.client_id == client_id).delete()
            session.query(Client).filter(Client.id == client_id).delete()
