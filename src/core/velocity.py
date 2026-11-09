"""Velocity counters from the live tables (account / business / global)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from db.models import Account, Assignment, ReviewAttempt
from db.session import session_scope


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def reviews_last_7d(account_id: uuid.UUID) -> int:
    with session_scope() as session:
        return (
            session.query(ReviewAttempt)
            .filter(ReviewAttempt.account_id == account_id, ReviewAttempt.ts >= _since(7))
            .count()
        )


def reviews_today(account_id: uuid.UUID | None = None, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with session_scope() as session:
        query = session.query(ReviewAttempt).filter(ReviewAttempt.ts >= day_start)
        if account_id is not None:
            query = query.filter(ReviewAttempt.account_id == account_id)
        return query.count()


def published_for_client(client_id: uuid.UUID) -> int:
    with session_scope() as session:
        return (
            session.query(Assignment)
            .filter(Assignment.client_id == client_id, Assignment.published_at.is_not(None))
            .count()
        )


def assignments_for_client(client_id: uuid.UUID) -> int:
    with session_scope() as session:
        return session.query(Assignment).filter(Assignment.client_id == client_id).count()


def last_publish_for_client(client_id: uuid.UUID) -> datetime | None:
    with session_scope() as session:
        row = (
            session.query(Assignment.published_at)
            .filter(Assignment.client_id == client_id, Assignment.published_at.is_not(None))
            .order_by(Assignment.published_at.desc())
            .first()
        )
    return row[0] if row else None


def categories_reviewed_last_week(account_id: uuid.UUID) -> set[str]:
    """Business categories this account touched in the last 7 days (assignment joins client)."""
    from db.models import Client

    with session_scope() as session:
        rows = (
            session.query(Client.category)
            .join(Assignment, Assignment.client_id == Client.id)
            .filter(Assignment.account_id == account_id, Assignment.published_at.is_not(None))
            .filter(Assignment.published_at >= _since(7))
            .all()
        )
    return {category for (category,) in rows if category}


def active_accounts_in_metro(metro_id: uuid.UUID) -> int:
    with session_scope() as session:
        return (
            session.query(Account)
            .filter(
                Account.metro_id == metro_id,
                Account.state.in_(["READY", "ACTIVE", "WARMING"]),
            )
            .count()
        )
