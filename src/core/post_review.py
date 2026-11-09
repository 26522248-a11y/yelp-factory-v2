"""Post-review warm mode: flags, session state, and the P0->P4 ladder budget.

After the review phase is finished the account only needs maintenance sessions
(spec v3.0 section 5): one session per day, <= 60 minutes, ladder P0 -> P4 with
every review action removed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from core.trust import WARM_MODES
from db.models import Account, WarmingPlan, WarmingSession
from db.session import session_scope
from obs.log import get_logger

log = get_logger("post_review")

REVIEWS_DONE_SUBSTATE = "reviews_done"
PLAN_STATUS = "post_review"

# Ladder run inside ONE session (spec 5.2 + trust additions). Budgets mirror
# core/budget.py PHASE_DEFAULTS with every review/photo-upload kind adjusted for
# profile completeness (uploads and friends feed Yelp trust the same way reviews do).
POST_REVIEW_BUDGET: list[tuple[str, dict[str, int]]] = [
    ("P0", {"search": 4, "pageview": 8, "scroll": 20, "save": 0, "vote": 0, "follow": 0, "friend": 0, "photo": 0, "upload_photo": 0, "checkin": 0}),
    # check-in moved to P1 (2026-11-09): it is the strongest geo signal and P4 often never runs
    ("P1", {"search": 4, "pageview": 8, "scroll": 20, "save": 3, "vote": 0, "follow": 0, "friend": 0, "photo": 2, "upload_photo": 1, "checkin": 1}),
    ("P2", {"search": 4, "pageview": 8, "scroll": 20, "save": 3, "vote": 5, "follow": 2, "friend": 1, "photo": 2, "upload_photo": 0, "checkin": 0}),
    ("P4", {"search": 1, "pageview": 2, "scroll": 10, "save": 1, "vote": 1, "follow": 0, "friend": 0, "photo": 1, "upload_photo": 0, "checkin": 0}),
]

REVIEW_KINDS = {"review"}  # never scheduled in this mode (spec 5.4)


def ladder_plan(resume_phase: str | None = None) -> list[tuple[str, dict[str, int]]]:
    """The remaining blocks; a crashed/half-finished session resumes at its block (E-75)."""
    plan = list(POST_REVIEW_BUDGET)
    if resume_phase:
        for index, (phase, _) in enumerate(plan):
            if phase == resume_phase:
                return plan[index:]
    return plan


# --------------------------------------------------------------------------------------
# reviews_done flag (spec 5.1)
# --------------------------------------------------------------------------------------


def mark_reviews_done(account_id: uuid.UUID) -> dict[str, Any]:
    with session_scope() as session:
        row = session.get(Account, account_id)
        if row is None:
            return {"ok": False, "reason": "account_missing"}
        row.reviews_done = True
        return {"ok": True, "account": str(account_id), "reviews_done": True}


def unmark_reviews_done(account_id: uuid.UUID) -> dict[str, Any]:
    with session_scope() as session:
        row = session.get(Account, account_id)
        if row is None:
            return {"ok": False, "reason": "account_missing"}
        row.reviews_done = False
        return {"ok": True, "account": str(account_id), "reviews_done": False}


def list_marked() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.query(Account).filter(Account.reviews_done.is_(True)).order_by(Account.created_at).all()
        return [{"account": str(r.id), "email": r.email, "state": r.state} for r in rows]


# --------------------------------------------------------------------------------------
# session state (resume / penalty) - kept in warming_plans.budget JSON
# --------------------------------------------------------------------------------------


def _plan_row(account_id: uuid.UUID, session) -> WarmingPlan | None:
    return (
        session.query(WarmingPlan)
        .filter(WarmingPlan.account_id == account_id, WarmingPlan.status == PLAN_STATUS)
        .order_by(WarmingPlan.id.desc())
        .first()
    )


def load_state(account_id: uuid.UUID) -> dict[str, Any]:
    with session_scope() as session:
        row = _plan_row(account_id, session)
        if row is None:
            return {"resume_phase": None, "penalty": {"until": None, "ratio": 1.0}}
        budget = dict(row.budget or {})
        return {
            "resume_phase": budget.get("resume_phase"),
            "penalty": budget.get("penalty") or {"until": None, "ratio": 1.0},
        }


def save_state(account_id: uuid.UUID, *, resume_phase: str | None, penalty: dict[str, Any] | None = None) -> None:
    with session_scope() as session:
        row = _plan_row(account_id, session)
        if row is None:
            row = WarmingPlan(account_id=account_id, phase=0, day=1, budget={}, status=PLAN_STATUS)
            session.add(row)
        budget = dict(row.budget or {})
        budget["resume_phase"] = resume_phase
        if penalty is not None:
            budget["penalty"] = penalty
        row.budget = budget


def apply_rate_penalty(account_id: uuid.UUID, *, days: int = 3, ratio: float = 0.5) -> dict[str, Any]:
    """429/403 twice in a row halves the budget for N days (mirror core/budget rule 8.4, E-77)."""
    until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    penalty = {"until": until, "ratio": ratio}
    state = load_state(account_id)
    save_state(account_id, resume_phase=state.get("resume_phase"), penalty=penalty)
    return penalty


def effective_ratio(account_id: uuid.UUID) -> float:
    state = load_state(account_id)
    penalty = state.get("penalty") or {}
    until = penalty.get("until")
    if not until:
        return 1.0
    try:
        if datetime.fromisoformat(until) > datetime.now(timezone.utc):
            return float(penalty.get("ratio", 1.0))
    except ValueError:
        pass
    return 1.0


# --------------------------------------------------------------------------------------
# cadence: 1 session/day (E-76), days-active gate (spec 5.5)
# --------------------------------------------------------------------------------------


def sessions_today(account_id: uuid.UUID, *, now: datetime | None = None, tz_name: str | None = None) -> int:
    """Sessions started since midnight in the account's metro timezone (2026-11-09)."""
    from zoneinfo import ZoneInfo

    now = now or datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("UTC")
    local = now.astimezone(tz)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    with session_scope() as session:
        rows = (
            session.query(WarmingSession.meta)
            .filter(
                WarmingSession.account_id == account_id,
                WarmingSession.mode.in_(WARM_MODES),
                WarmingSession.started_at >= day_start,
            )
            .all()
        )
    # same rule as warm evidence (core/trust.py): a seeded/imported row is not a
    # session the account actually ran, and both ladders count as real cadence.
    return sum(1 for (meta,) in rows if not (meta or {}).get("seed"))


def days_active(account_id: uuid.UUID) -> int:
    with session_scope() as session:
        rows = (
            session.query(WarmingSession.started_at)
            .filter(
                WarmingSession.account_id == account_id,
                WarmingSession.mode.in_(WARM_MODES),
            )
            .all()
        )
    return len({(ts[0] or datetime.now(timezone.utc)).date().isoformat() for ts in rows})


def session_count(account_id: uuid.UUID) -> int:
    """Real sessions run so far on either ladder (warm + post_review), seed rows excluded.

    Counting only ``post_review`` made a normally-warming account report 0 sessions, so
    the P0->P4 ladder gate (``unlocked_phases_by_session``) never left P0 and the daily
    cap in ``orchestrator.run_post_review_warm`` read 0 as well. Both ladders are real
    work; ``meta.seed`` rows are not (same definition as warm evidence in core/trust.py).
    """
    with session_scope() as session:
        rows = (
            session.query(WarmingSession.meta)
            .filter(
                WarmingSession.account_id == account_id,
                WarmingSession.mode.in_(WARM_MODES),
            )
            .all()
        )
    return sum(1 for (meta,) in rows if not (meta or {}).get("seed"))


def photos_uploaded(account_id: uuid.UUID) -> int:
    from db.models import ActionLog

    with session_scope() as session:
        return session.query(ActionLog).filter(ActionLog.account_id == account_id, ActionLog.kind == "upload_photo").count()


def unlocked_phases(active_days: int) -> set[str]:
    """Kept for backward compatibility - prefer unlocked_phases_by_session."""
    return unlocked_phases_by_session(active_days)


def unlocked_phases_by_session(sessions: int) -> set[str]:
    """Ladder gate by REAL session count (2026-11-09): 1-2 -> P0/P1, 3+ -> P2, 5+ -> P4."""
    unlocked = {"P0"}
    if sessions >= 1:
        unlocked.add("P1")
    if sessions >= 3:
        unlocked.add("P2")
    if sessions >= 5:
        unlocked.add("P4")
    return unlocked


def due_accounts(limit: int = 20, *, now: datetime | None = None) -> list[uuid.UUID]:
    """Accounts flagged reviews_done that still owe a session today (metro timezone)."""
    from db.models import Account, Metro

    now = now or datetime.now(timezone.utc)
    with session_scope() as session:
        rows = (
            session.query(Account.id, Metro.timezone)
            .outerjoin(Metro, Metro.id == Account.metro_id)
            .filter(Account.reviews_done.is_(True))
            .order_by(Account.created_at)
            .limit(200)
            .all()
        )
    due = []
    for account_id, tz_name in rows:
        if sessions_today(account_id, now=now, tz_name=tz_name) == 0:
            due.append(account_id)
        if len(due) >= limit:
            break
    return due


def within_window(now: datetime | None = None, *, start: str = "08:00", end: str = "20:00") -> bool:
    # Local clock, matching the factory scheduler's working window (spec 5.6).
    now = now or datetime.now()
    current = now.strftime("%H:%M")
    return start <= current <= end


def within_account_window(tz_name: str | None, now: datetime | None = None, *, start: str = "08:00", end: str = "20:00") -> bool:
    """Scheduling window in the *metro's* local time, not the host's (2026-11-09)."""
    from zoneinfo import ZoneInfo

    now = now or datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(tz_name or "America/New_York")
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("America/New_York")
    local = now.astimezone(tz)
    current = local.strftime("%H:%M")
    return start <= current <= end


# --------------------------------------------------------------------------------------
# metro history (geographic consistency - local reviewer signal)
# --------------------------------------------------------------------------------------

LOCAL_HISTORY_DAYS_FOR_REVIEW = 3  # pump local activity before reviewing a foreign-city client


def record_metro_visit(state: dict, city: str, *, today: str | None = None) -> dict:
    """Track one local-activity day per metro inside the per-account state file."""
    today = today or date.today().isoformat()
    metro = dict(state.get("metro") or {})
    last = state.get("metro_last")
    if last != [city, today]:
        metro[city] = int(metro.get(city, 0)) + 1
        state["metro"] = metro
        state["metro_last"] = [city, today]
    return state


def has_local_history(state: dict, city: str, *, days: int = LOCAL_HISTORY_DAYS_FOR_REVIEW) -> bool:
    return int((state.get("metro") or {}).get(city, 0)) >= days
