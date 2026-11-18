"""Read-only account listing for the operator console.

The console never reads the database directly; this module is the single place
that turns `accounts` rows into the JSON shape in `yfcp/docs/engine-contract.md`.

Kept separate from `api/admin.py` so the payload builder and filter validation
can be unit-tested without a database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from db.models import Account, AccountState, Assignment, Metro, Profile, TrustScore, WarmingPlan

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
PUBLISHED_STATUSES = ("published", "published_ok")
SORTABLE = {"created_at", "email", "state", "trust_score", "last_active_at"}


@dataclass(frozen=True)
class AccountFilters:
    states: tuple[str, ...] = ()
    city: str | None = None
    batch_id: uuid.UUID | None = None
    q: str | None = None
    blacklisted: bool | None = None
    mode: str | None = None
    sort: str = "created_at"
    descending: bool = True
    limit: int = DEFAULT_LIMIT
    offset: int = 0


def _parse_bool(value: str | bool | None) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    raise ValueError(f"blacklisted must be true|false, got {value!r}")


def parse_filters(
    *,
    state: str | None = None,
    city: str | None = None,
    batch_id: str | None = None,
    q: str | None = None,
    blacklisted: str | bool | None = None,
    mode: str | None = None,
    sort: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> AccountFilters:
    """Validate query parameters. Raises ValueError (mapped to HTTP 400)."""
    known = {member.value for member in AccountState}
    states = tuple(
        part.strip().upper() for part in (state or "").split(",") if part.strip()
    )
    unknown = [item for item in states if item not in known]
    if unknown:
        raise ValueError(f"unknown state(s): {', '.join(unknown)}")

    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    parsed_batch: uuid.UUID | None = None
    if batch_id:
        try:
            parsed_batch = uuid.UUID(batch_id)
        except ValueError as exc:
            raise ValueError("batch_id must be a UUID") from exc

    sort_key = (sort or "created_at").lstrip("-")
    if sort_key not in SORTABLE:
        raise ValueError(f"sort must be one of: {', '.join(sorted(SORTABLE))}")

    normalized_mode = (mode or "").strip().lower() or None
    if normalized_mode not in {None, "post_review", "full_warm"}:
        # `view_only` is a console concept with no column yet; ignore it rather
        # than hide every row.
        normalized_mode = None

    return AccountFilters(
        states=states,
        city=(city or "").strip() or None,
        batch_id=parsed_batch,
        q=(q or "").strip() or None,
        blacklisted=_parse_bool(blacklisted),
        mode=normalized_mode,
        sort=sort_key,
        descending=(sort or "").startswith("-") or sort is None,
        limit=limit,
        offset=offset,
    )


def _latest_trust():
    return (
        select(TrustScore.account_id, TrustScore.score, TrustScore.components)
        .distinct(TrustScore.account_id)
        .order_by(TrustScore.account_id, TrustScore.ts.desc())
        .subquery("latest_trust")
    )


def _latest_plan():
    return (
        select(WarmingPlan.account_id, WarmingPlan.phase, WarmingPlan.day)
        .distinct(WarmingPlan.account_id)
        .order_by(WarmingPlan.account_id, WarmingPlan.day.desc())
        .subquery("latest_plan")
    )


def _published_reviews():
    return (
        select(
            Assignment.account_id,
            func.count().label("reviews_posted"),
        )
        .where(Assignment.status.in_(PUBLISHED_STATUSES))
        .group_by(Assignment.account_id)
        .subquery("published_reviews")
    )


def _conditions(filters: AccountFilters) -> list[Any]:
    conditions: list[Any] = []
    if filters.states:
        conditions.append(Account.state.in_(filters.states))
    if filters.city:
        conditions.append(Account.city.ilike(f"%{filters.city}%"))
    if filters.batch_id:
        conditions.append(Account.batch_id == filters.batch_id)
    if filters.blacklisted is not None:
        conditions.append(Account.blacklisted.is_(filters.blacklisted))
    if filters.mode == "post_review":
        conditions.append(Account.reviews_done.is_(True))
    elif filters.mode == "full_warm":
        conditions.append(Account.reviews_done.is_(False))
    if filters.q:
        pattern = f"%{filters.q}%"
        conditions.append(
            or_(
                Account.email.ilike(pattern),
                Account.first_name.ilike(pattern),
                Account.last_name.ilike(pattern),
                Account.city.ilike(pattern),
            )
        )
    return conditions


def account_statement(filters: AccountFilters) -> Select:
    """The joined read used by both list and detail."""
    trust = _latest_trust()
    plan = _latest_plan()
    reviews = _published_reviews()

    stmt = (
        select(
            Account,
            Metro,
            trust.c.score,
            trust.c.components,
            plan.c.phase,
            plan.c.day,
            Profile.gpm_profile_id,
            reviews.c.reviews_posted,
        )
        .outerjoin(Metro, Account.metro_id == Metro.id)
        .outerjoin(trust, trust.c.account_id == Account.id)
        .outerjoin(plan, plan.c.account_id == Account.id)
        .outerjoin(Profile, Account.profile_id == Profile.id)
        .outerjoin(reviews, reviews.c.account_id == Account.id)
    )
    conditions = _conditions(filters)
    if conditions:
        stmt = stmt.where(*conditions)

    if filters.sort == "trust_score":
        column = func.coalesce(trust.c.score, 0)
    elif filters.sort == "last_active_at":
        column = func.coalesce(Account.last_probe_at, Account.activated_at, Account.created_at)
    else:
        column = {
            "email": Account.email,
            "state": Account.state,
            "created_at": Account.created_at,
        }[filters.sort]

    stmt = stmt.order_by(column.desc() if filters.descending else column.asc(), Account.id)
    return stmt


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def account_payload(
    account: Account,
    metro: Metro | None,
    score: int | None,
    components: dict | None,
    phase: int | None,
    day: int | None,
    gpm_profile_id: str | None,
    reviews_posted: int | None,
) -> dict:
    """Map a row to the console contract. Pure function: unit-test friendly."""
    plan_phase = min(max(int(phase or 0), 0), 4)
    return {
        "id": str(account.id),
        "email": account.email,
        "first_name": account.first_name,
        "last_name": account.last_name,
        "state": account.state,
        "substate": account.substate,
        "city": account.city,
        "state_code": metro.state if metro else "",
        "zip": account.zip,
        "timezone": metro.timezone if metro else "America/New_York",
        "trust_score": int(score or 0),
        "trust": components or {},
        "reviews_done": int(bool(account.reviews_done)),
        "reviews_posted": int(reviews_posted or 0),
        "phase": f"P{plan_phase}",
        "phase_day": int(day or 0),
        "tier": account.tier or "Loai",
        "blacklisted": bool(account.blacklisted),
        "gpm_profile_id": gpm_profile_id or "",
        "proxy": account.proxy_ip or "",
        "proxy_city": metro.name if metro else account.city,
        "batch_id": str(account.batch_id) if account.batch_id else None,
        "mode": "post_review" if account.reviews_done else "full_warm",
        "adopted_at": iso(account.adopted_at),
        "city_changed_at": iso(account.city_changed_at),
        "last_active_at": iso(account.last_probe_at or account.activated_at or account.created_at),
        "created_at": iso(account.created_at),
        "profile_complete": 100 if account.profile_complete else 0,
        "sessions_7d": 0,
        "photos": 0,
        "use_count": int(account.use_count or 0),
        "supplier": account.supplier,
        "home_city": account.home_city,
    }


def _row_payload(row) -> dict:
    (
        account,
        metro,
        score,
        components,
        phase,
        day,
        gpm_profile_id,
        reviews_posted,
    ) = row
    return account_payload(
        account, metro, score, components, phase, day, gpm_profile_id, reviews_posted
    )


def list_accounts(session: Session, filters: AccountFilters) -> dict:
    conditions = _conditions(filters)
    total_stmt = select(func.count()).select_from(Account)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = int(session.execute(total_stmt).scalar_one())

    stmt = account_statement(filters).limit(filters.limit).offset(filters.offset)
    rows = session.execute(stmt).all()
    return {
        "items": [_row_payload(row) for row in rows],
        "total": total,
        "limit": filters.limit,
        "offset": filters.offset,
    }


def get_account(session: Session, account_id: uuid.UUID) -> dict | None:
    filters = AccountFilters(limit=1, offset=0)
    stmt = account_statement(filters).where(Account.id == account_id).limit(1)
    row = session.execute(stmt).first()
    return _row_payload(row) if row else None
