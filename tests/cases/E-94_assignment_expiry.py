"""E-94: planned assignments expire after 7 days instead of posting late."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.assignments import ASSIGNMENT_EXPIRY_DAYS, due_assignments
from core.clients import ensure_metro
from db.models import Assignment, Client
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready")


def test_stale_planned_assignment_is_expired_not_posted(make_account):
    metro = ensure_metro("Expiry Metro, NY")
    account = make_account()
    client_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            Client(
                id=client_id,
                business_name="Expiry Diner",
                metro_id=metro,
                category="restaurants",
                yelp_biz_id=f"expiry-{uuid.uuid4().hex[:8]}",
                facts={"menu": ["soup"], "price_examples": ["$7"]},
            )
        )
    with session_scope() as session:
        session.add(
            Assignment(
                id=assignment_id,
                client_id=client_id,
                account_id=account.id,
                status="planned",
                review_due_at=datetime.now(timezone.utc) - timedelta(days=ASSIGNMENT_EXPIRY_DAYS + 3),
            )
        )
    try:
        due = due_assignments(limit=10)
        assert all(item["assignment_id"] != str(assignment_id) for item in due)
        with session_scope() as session:
            assert session.get(Assignment, assignment_id).status == "expired"
    finally:
        with session_scope() as session:
            session.query(Assignment).filter(Assignment.client_id == client_id).delete()
            session.query(Client).filter(Client.id == client_id).delete()
