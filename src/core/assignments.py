"""Review assignment planner (2026-11-09 policy).

Hard rules:
* account and client must share the same metro (Yelp "local reviewer" signal);
* an account only reviews a business when ``trust.review_eligible`` passes (75+);
* at most 2 accounts per business, spaced 5-10 days apart, never the same day;
* an account publishes at most 2 reviews per week and never 2 clients of the same
  category within one week;
* after 3 consecutive weeks of reviews the account rests 5-7 days;
* the daily assignment allowance is scaled by the volume governor.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from core.velocity import (
    categories_reviewed_last_week,
    last_publish_for_client,
    published_for_client,
    reviews_last_7d,
)
from core.volume import effective_multiplier, pick_slot_hour
from db.models import Account, Assignment, Client, Metro
from db.session import session_scope
from obs.log import get_logger

log = get_logger("assignments")

MAX_ACCOUNTS_PER_BUSINESS = 2
REVIEWS_PER_ACCOUNT_WEEK = 2
SPACING_DAYS = (5, 10)
REST_DAYS_AFTER_3_WEEKS = 7
TRUST_REVIEW_THRESHOLD = 75
REVIEW_MIN_DAYS_ACTIVE = 7       # hard gate independent of trust (2026-11-09)
REVIEW_MIN_PHOTOS_UPLOADED = 8   # profile must show real photo history before reviews
MAX_WARRANTY_REPLACEMENTS = 2
REPLACEMENT_MIN_GAP_DAYS = 7
ASSIGNMENT_EXPIRY_DAYS = 7  # planned assignments older than this are never posted
DEFAULT_TZ = "America/New_York"


def _profile_ready(account_id: uuid.UUID) -> bool:
    """Hard gates independent of trust: enough active days and uploaded photos."""
    from core.post_review import days_active as _days, photos_uploaded as _photos

    return _days(account_id) >= REVIEW_MIN_DAYS_ACTIVE and _photos(account_id) >= REVIEW_MIN_PHOTOS_UPLOADED


def _trust_for(session, account_id: uuid.UUID, cache: dict | None = None) -> int:
    """Trust is always derived from real history - a stored/seeded number cannot open
    the review gate (2026-11-09)."""
    if cache is not None and account_id in cache:
        return cache[account_id]
    from core.trust import compute_trust

    score = compute_trust(account_id).score
    if cache is not None:
        cache[account_id] = score
    return score


def _weeks_with_reviews(session, account_id: uuid.UUID) -> int:
    """Consecutive ISO weeks (up to 3) with at least one review."""
    from db.models import ReviewAttempt

    rows = (
        session.query(ReviewAttempt.ts)
        .filter(ReviewAttempt.account_id == account_id, ReviewAttempt.ts >= datetime.now(timezone.utc) - timedelta(days=28))
        .all()
    )
    weeks = {(ts.astimezone(timezone.utc).isocalendar()[1]) for (ts,) in rows if ts is not None}
    if not weeks:
        return 0
    now_week = datetime.now(timezone.utc).isocalendar()[1]
    consecutive = 0
    week = now_week
    while consecutive < 3:
        previous = (week - 1) if week > 1 else 52
        if previous in weeks or week in weeks:
            consecutive += 1
            week = previous
        else:
            break
    return consecutive


def needs_rest(session, account_id: uuid.UUID) -> bool:
    if _weeks_with_reviews(session, account_id) < 3:
        return False
    from db.models import ReviewAttempt

    last = (
        session.query(ReviewAttempt.ts)
        .filter(ReviewAttempt.account_id == account_id)
        .order_by(ReviewAttempt.ts.desc())
        .first()
    )
    if not last or last[0] is None:
        return False
    return (datetime.now(timezone.utc) - last[0]) < timedelta(days=REST_DAYS_AFTER_3_WEEKS - 1)


def plan_assignments(limit: int | None = None, *, now: datetime | None = None) -> list[dict]:
    """Create planned assignments for due clients; returns the created rows."""
    now = now or datetime.now(timezone.utc)
    allowance = limit if limit is not None else max(1, int(5 * effective_multiplier(now)))
    if effective_multiplier(now) <= 0:
        return []

    created: list[dict] = []
    trust_cache: dict[uuid.UUID, int] = {}
    with session_scope() as session:
        clients = (
            session.query(Client)
            .filter(Client.metro_id.is_not(None))
            .order_by(Client.created_at)
            .limit(200)
            .all()
        )
        for client in clients:
            if len(created) >= allowance:
                break
            # count planned + published (not only published) so repeated assign sweeps
            # never stack extra assignments for the same client
            existing_active = (
                session.query(Assignment)
                .filter(Assignment.client_id == client.id, Assignment.status.in_(["planned", "published", "published_ok"]))
                .count()
            )
            if existing_active >= MAX_ACCOUNTS_PER_BUSINESS:
                continue
            metro_row = session.get(Metro, client.metro_id)
            tz = ZoneInfo(metro_row.timezone if metro_row and metro_row.timezone else DEFAULT_TZ)

            candidates = (
                session.query(Account)
                .filter(
                    Account.metro_id == client.metro_id,
                    Account.state.in_(["READY", "ACTIVE"]),
                )
                .order_by(Account.created_at)
                .all()
            )
            random.shuffle(candidates)
            for account in candidates:
                if reviews_last_7d(account.id) >= REVIEWS_PER_ACCOUNT_WEEK:
                    continue
                if _trust_for(session, account.id, trust_cache) < TRUST_REVIEW_THRESHOLD:
                    continue
                if not _profile_ready(account.id):
                    continue
                if needs_rest(session, account.id):
                    continue
                if client.category in categories_reviewed_last_week(account.id):
                    continue
                # already assigned this client? (unique constraint backup)
                existing = (
                    session.query(Assignment.id)
                    .filter(Assignment.client_id == client.id, Assignment.account_id == account.id)
                    .first()
                )
                if existing:
                    continue

                last = last_publish_for_client(client.id)
                gap_days = random.randint(*SPACING_DAYS)
                earliest = now
                if last is not None:
                    earliest = max(now, last + timedelta(days=gap_days))
                local = earliest.astimezone(tz)
                due_local = local.replace(
                    hour=pick_slot_hour(random.Random()), minute=random.randint(0, 59), second=0, microsecond=0
                )
                due = due_local.astimezone(timezone.utc)
                if due < now:
                    due = due + timedelta(minutes=random.randint(30, 120))

                try:
                    with session.begin_nested():
                        session.add(
                            Assignment(
                                client_id=client.id,
                                account_id=account.id,
                                status="planned",
                                review_due_at=due,
                                meta={"category": client.category, "planned_by": "planner", "timezone": str(tz)},
                            )
                        )
                except IntegrityError:
                    # uq_assignment_client_account: one account reviews a business once, forever
                    log.info("assignment_duplicate_skipped", client=str(client.id), account=str(account.id))
                    continue
                created.append(
                    {
                        "client": client.business_name,
                        "account": str(account.id),
                        "due_at": due.isoformat(),
                        "timezone": str(tz),
                    }
                )
                break
    log.info("assignments_planned", count=len(created), allowance=allowance)
    return created


def plan_replacement(client_id: uuid.UUID, old_account_id: uuid.UUID, *, now: datetime | None = None) -> dict | None:
    """A filtered review is replaced by another account (>=7 days later, warranty cap).

    The replacement counts against the client's warranty quota (MAX_WARRANTY_REPLACEMENTS).
    """
    now = now or datetime.now(timezone.utc)
    with session_scope() as session:
        client = session.get(Client, client_id)
        if client is None or client.metro_id is None:
            return None
        warranties = (
            session.query(Assignment)
            .filter(
                Assignment.client_id == client_id,
                Assignment.meta["kind"].astext == "warranty",
            )
            .count()
        )
        if warranties >= MAX_WARRANTY_REPLACEMENTS:
            log.warning("warranty_cap_reached", client=str(client_id), count=warranties)
            return None
        metro_row = session.get(Metro, client.metro_id)
        tz = ZoneInfo(metro_row.timezone if metro_row and metro_row.timezone else DEFAULT_TZ)

        candidates = (
            session.query(Account)
            .filter(
                Account.metro_id == client.metro_id,
                Account.state.in_(["READY", "ACTIVE"]),
                Account.id != old_account_id,
            )
            .order_by(Account.created_at)
            .all()
        )
        trust_cache: dict[uuid.UUID, int] = {}
        random.shuffle(candidates)
        for account in candidates:
            if reviews_last_7d(account.id) >= REVIEWS_PER_ACCOUNT_WEEK:
                continue
            if _trust_for(session, account.id, trust_cache) < TRUST_REVIEW_THRESHOLD:
                continue
            if not _profile_ready(account.id):
                continue
            if needs_rest(session, account.id):
                continue
            if session.query(Assignment.id).filter(
                Assignment.client_id == client_id, Assignment.account_id == account.id
            ).first():
                continue
            due_local = (now + timedelta(days=REPLACEMENT_MIN_GAP_DAYS)).astimezone(tz).replace(
                hour=pick_slot_hour(random.Random()), minute=random.randint(0, 59), second=0, microsecond=0
            )
            due = due_local.astimezone(timezone.utc)
            try:
                with session.begin_nested():
                    session.add(
                        Assignment(
                            client_id=client_id,
                            account_id=account.id,
                            status="planned",
                            review_due_at=due,
                            meta={"kind": "warranty", "warranty_for": str(old_account_id), "timezone": str(tz)},
                        )
                    )
            except IntegrityError:
                continue
            log.info("warranty_replacement_planned", client=str(client_id), account=str(account.id), due=due.isoformat())
            return {"client": client.business_name, "account": str(account.id), "due_at": due.isoformat()}
    return None


def due_assignments(limit: int = 5, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    # stale planned assignments expire instead of being posted weeks late (test design #5)
    with session_scope() as session:
        session.query(Assignment).filter(
            Assignment.status == "planned",
            Assignment.review_due_at.is_not(None),
            Assignment.review_due_at < now - timedelta(days=ASSIGNMENT_EXPIRY_DAYS),
        ).update({"status": "expired"}, synchronize_session=False)
    with session_scope() as session:
        rows = (
            session.query(Assignment, Client, Account)
            .join(Client, Client.id == Assignment.client_id)
            .join(Account, Account.id == Assignment.account_id)
            .filter(
                Assignment.status == "planned",
                Assignment.review_due_at.is_not(None),
                Assignment.review_due_at <= now,
            )
            .order_by(Assignment.review_due_at)
            .limit(limit)
            .all()
        )
        return [
            {
                "assignment_id": str(a.id),
                "account_id": str(acc.id),
                "client_id": str(c.id),
                "business_name": c.business_name,
                "yelp_biz_id": c.yelp_biz_id,
                "category": c.category,
                "facts": dict(c.facts or {}),
                "due_at": a.review_due_at.isoformat() if a.review_due_at else None,
            }
            for a, c, acc in rows
        ]


def mark_published(assignment_id: uuid.UUID, *, review_attempt_id: uuid.UUID | None = None) -> None:
    with session_scope() as session:
        row = session.get(Assignment, assignment_id)
        if row is not None:
            row.status = "published"
            row.published_at = datetime.now(timezone.utc)
            if review_attempt_id is not None:
                row.meta = {**(row.meta or {}), "review_attempt_id": str(review_attempt_id)}


def mark_failed(assignment_id: uuid.UUID, reason: str) -> None:
    with session_scope() as session:
        row = session.get(Assignment, assignment_id)
        if row is not None:
            row.status = "failed"
            row.meta = {**(row.meta or {}), "error": reason[:200]}


def due_for_check(hours: int = 72, limit: int = 20) -> list[dict]:
    """Published assignments older than ``hours`` that were never re-checked."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with session_scope() as session:
        rows = (
            session.query(Assignment, Client, Account)
            .join(Client, Client.id == Assignment.client_id)
            .join(Account, Account.id == Assignment.account_id)
            .filter(
                Assignment.status == "published",
                Assignment.published_at.is_not(None),
                Assignment.published_at <= cutoff,
                Assignment.filtered_at.is_(None),
            )
            .order_by(Assignment.published_at)
            .limit(limit)
            .all()
        )
        return [
            {
                "assignment_id": str(a.id),
                "account_id": str(acc.id),
                "client_id": str(c.id),
                "yelp_user_id": acc.yelp_user_id,
                "business_name": c.business_name,
                "yelp_biz_id": c.yelp_biz_id,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a, c, acc in rows
        ]


def mark_filtered(assignment_id: uuid.UUID, *, filtered: bool) -> None:
    with session_scope() as session:
        row = session.get(Assignment, assignment_id)
        if row is not None:
            if filtered:
                row.filtered_at = datetime.now(timezone.utc)
                row.status = "filtered"
            else:
                row.status = "published_ok"
                row.meta = {**(row.meta or {}), "checked_at": datetime.now(timezone.utc).isoformat()}


def metro_cap_reached(metro_name: str) -> bool:
    with session_scope() as session:
        metro = session.query(Metro).filter(Metro.name == metro_name).one_or_none()
        if metro is None:
            return False
        count = (
            session.query(Account)
            .filter(Account.metro_id == metro.id, Account.state.notin_(["RETIRED", "BANNED", "DEAD"]))
            .count()
        )
    return count >= 8
