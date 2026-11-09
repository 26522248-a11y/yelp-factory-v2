"""Account trust score + action gates (warming spec v1.0, section 0).

Warm evidence definition (fixed 2026-11-09, decision by MINH): trust must be derived
from real behaviour, so *every* real warming session counts - not only the
``post_review`` maintenance mode. The previous filter (``mode == "post_review"``) made
the ``warm`` component 0 for the whole pre-review life of an account, which capped the
theoretical score at 60 < 75 and made the review gate unreachable (deadlock).

A warming session is evidence when ALL of the following hold:

1. ``mode`` is in :data:`WARM_MODES` (``"warm"`` = normal ladder, ``"post_review"`` =
   maintenance ladder). Any future mode must be added here explicitly.
2. ``started_at`` is within :data:`WARM_WINDOW_DAYS` (30) of "now".
3. It carries real work: ``max(warming_sessions.actions, count(action_log rows for that
   session)) >= WARM_MIN_ACTIONS``. Opening Yelp and idling is not evidence.
4. ``meta.seed`` is not true - seeded/imported history is never evidence.

Points: ``min(18, sessions*2) + min(12, distinct active days*1.5)`` = 30 max.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from db.models import Account, ActionLog, Event, ReviewAttempt, TrustScore
from db.session import session_scope
from obs.log import get_logger

log = get_logger("trust")

WEIGHTS = {
    "age": 15,
    "profile": 15,
    "consistency": 12,
    "diversity": 18,
    "warm": 30,      # real warm history (sessions + active days) - see warm evidence above
    "content": 20,   # reviews
    "risk": -20,
}

RISK_PENALTY = {
    "http_429": 3,
    "http_403": 5,
    "captcha": 4,
    "identity_check": 15,
    "filtered_review": 8,
    "sms_fail": 2,
    "gpm_down": 1,
}

REVIEW_THRESHOLD = 75
REVIEW_MIN_AGE_DAYS = 11
REVIEW_MIN_SESSIONS_7D = 6

# --- warm evidence (single source of truth) -------------------------------------------
WARM_MODES = ("warm", "post_review")
WARM_WINDOW_DAYS = 30
WARM_MIN_ACTIONS = 3
WARM_SESSION_POINTS = 2.0
WARM_SESSION_CAP = 18.0
WARM_DAY_POINTS = 1.5
WARM_DAY_CAP = 12.0

# Photo uploads are *profile building*, i.e. they create the evidence the review gate
# later reads (assignments._profile_ready needs photos_uploaded >= 8). Gating them at 75
# would keep them behind the very gate they feed, so they unlock early.
UPLOAD_PHOTO_MIN_SCORE = 25


@dataclass
class TrustBreakdown:
    age: float = 0
    profile: float = 0
    consistency: float = 0
    diversity: float = 0
    warm: float = 0
    content: float = 0
    risk: float = 0
    evidence: dict = field(default_factory=dict)

    @property
    def score(self) -> int:
        raw = self.age + self.profile + self.consistency + self.diversity + self.warm + self.content + self.risk
        return max(0, min(100, int(round(raw))))

    def as_dict(self) -> dict:
        data = asdict(self)
        data["score"] = self.score
        return data


@dataclass
class WarmEvidence:
    """How the ``warm`` component was earned - exposed for CLI/ops and for tests."""

    sessions: int = 0          # evidence sessions inside the window
    sessions_seen: int = 0     # all sessions inside the window, before filtering
    active_days: int = 0
    rejected_no_work: int = 0  # sessions with < WARM_MIN_ACTIONS real actions
    rejected_seed: int = 0
    points: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _age_component(account: Account, now: datetime) -> float:
    created = account.created_at or now
    days = max(0.0, (now - created).total_seconds() / 86400)
    return min(15.0, days * 0.75)


def _profile_component(account: Account) -> float:
    score = 0.0
    # profile_complete is set only after the avatar renders in the DOM (orchestrator),
    # so it is a trustworthy signal that the profile is inhabited.
    if account.avatar_path or bool(getattr(account, "profile_complete", False)):
        score += 4
    if account.first_name and account.last_name:
        score += 2
    if account.city and account.address_line:
        score += 3
    if account.birth_date:
        score += 2
    if account.email:
        score += 2
    if account.phone_e164:
        score += 2
    return min(15.0, score)


def _consistency_component(account: Account, actions: list[ActionLog]) -> float:
    if not actions:
        return 0.0
    ips = {a.meta.get("proxy_ip") for a in actions if a.meta and a.meta.get("proxy_ip")}
    score = 8.0
    if len(ips) <= 1:
        score += 4
    elif len(ips) == 2:
        score += 2
    if account.profile_id:
        score += 2
    return min(12.0, score)


def _diversity_component(actions: list[ActionLog]) -> float:
    kinds = {a.kind for a in actions}
    targets = {a.target for a in actions if a.target}
    score = min(10.0, len(kinds) * 1.5) + min(8.0, len(targets) * 0.5)
    return min(18.0, score)


def warm_evidence_from_rows(rows: list[tuple]) -> WarmEvidence:
    """Pure scoring of warm evidence.

    ``rows`` is a sequence of ``(started_at, actions, meta, logged_actions)`` where
    ``logged_actions`` is the number of ``action_log`` rows tied to that session.
    Keeping this pure means the formula is testable without a database.
    """
    evidence = WarmEvidence(sessions_seen=len(rows))
    days: set[str] = set()
    for started_at, actions, meta, logged_actions in rows:
        meta = meta or {}
        if meta.get("seed"):
            evidence.rejected_seed += 1
            continue
        work = max(int(actions or 0), int(logged_actions or 0))
        if work < WARM_MIN_ACTIONS:
            evidence.rejected_no_work += 1
            continue
        evidence.sessions += 1
        if started_at is not None:
            days.add(started_at.date().isoformat())
    evidence.active_days = len(days)
    evidence.points = min(WARM_SESSION_CAP, evidence.sessions * WARM_SESSION_POINTS) + min(
        WARM_DAY_CAP, evidence.active_days * WARM_DAY_POINTS
    )
    return evidence


def warm_evidence(account_id: uuid.UUID, *, now: datetime | None = None) -> WarmEvidence:
    from db.models import WarmingSession

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WARM_WINDOW_DAYS)
    with session_scope() as session:
        sessions = (
            session.query(WarmingSession.id, WarmingSession.started_at, WarmingSession.actions, WarmingSession.meta)
            .filter(
                WarmingSession.account_id == account_id,
                WarmingSession.mode.in_(WARM_MODES),
                WarmingSession.started_at >= cutoff,
            )
            .all()
        )
        if not sessions:
            return WarmEvidence()
        per_session = dict(
            session.query(ActionLog.session_id, func.count(ActionLog.id))
            .filter(ActionLog.account_id == account_id, ActionLog.session_id.isnot(None))
            .group_by(ActionLog.session_id)
            .all()
        )
    rows = [
        (started_at, actions, meta, per_session.get(session_id, 0))
        for session_id, started_at, actions, meta in sessions
    ]
    return warm_evidence_from_rows(rows)


def _warm_component(account_id: uuid.UUID, now: datetime) -> float:
    return warm_evidence(account_id, now=now).points


def _content_component(reviews: list[ReviewAttempt]) -> float:
    if not reviews:
        return 0.0
    score = 0.0
    for review in reviews[-5:]:
        if 80 <= review.words <= 200:
            score += 2.0
        if review.photo:
            score += 1.0
        if review.status == "published":
            score += 1.0
        if review.filtered_at is not None:
            score -= 1.0
    return max(0.0, min(20.0, score))


def _risk_component(account_id: uuid.UUID, now: datetime) -> float:
    cutoff = now - timedelta(days=30)
    with session_scope() as session:
        events = session.execute(
            select(Event.code).where(Event.account_id == account_id, Event.ts >= cutoff)
        ).all()
    penalty = 0.0
    for (code,) in events:
        if not code:
            continue
        penalty += RISK_PENALTY.get(code, 1)
    return -min(20.0, penalty)


def compute_trust(account_id: uuid.UUID, *, now: datetime | None = None) -> TrustBreakdown:
    now = now or datetime.now(timezone.utc)
    with session_scope() as session:
        account = session.get(Account, account_id)
        if account is None:
            return TrustBreakdown()
        actions = session.scalars(
            select(ActionLog).where(ActionLog.account_id == account_id, ActionLog.ts >= now - timedelta(days=7))
        ).all()
        reviews = session.scalars(
            select(ReviewAttempt).where(ReviewAttempt.account_id == account_id).order_by(ReviewAttempt.ts)
        ).all()
        breakdown = TrustBreakdown(
            age=_age_component(account, now),
            profile=_profile_component(account),
            consistency=_consistency_component(account, actions),
            diversity=_diversity_component(actions),
            warm=_warm_component(account_id, now),
            content=_content_component(reviews),
        )
        breakdown.risk = _risk_component(account_id, now)
    return breakdown


def record_trust(account_id: uuid.UUID, breakdown: TrustBreakdown | None = None) -> int:
    breakdown = breakdown or compute_trust(account_id)
    with session_scope() as session:
        session.add(TrustScore(account_id=account_id, score=breakdown.score, components=breakdown.as_dict()))
    return breakdown.score


def latest_trust(account_id: uuid.UUID) -> int:
    with session_scope() as session:
        row = session.scalars(
            select(TrustScore).where(TrustScore.account_id == account_id).order_by(TrustScore.id.desc()).limit(1)
        ).first()
        if row is not None:
            return row.score
    return compute_trust(account_id).score


def recompute_all(limit: int = 500) -> dict:
    """Derive trust from real history (actions/reviews/age) and overwrite stored values.

    Seeded/manual trust scores are never authoritative: the planner calls
    ``compute_trust`` directly, and this job keeps the snapshots honest.
    """
    from db.models import Account

    with session_scope() as session:
        ids = [row[0] for row in session.query(Account.id).limit(limit).all()]
    scores: dict[str, int] = {}
    for account_id in ids:
        try:
            scores[str(account_id)] = record_trust(account_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("trust_recompute_failed", account_id=str(account_id), error=str(exc)[:150])
    below = sum(1 for score in scores.values() if score < REVIEW_THRESHOLD)
    return {"count": len(scores), "below_review_threshold": below, "scores": scores}


def allowed_kinds(score: int) -> set[str]:
    """Deterministic gate: which action kinds an account may perform at this score."""
    kinds = {"pageview", "search", "scroll", "session"}
    if score >= UPLOAD_PHOTO_MIN_SCORE:
        # profile building: must be available long before the review gate it feeds
        kinds |= {"upload_photo"}
    if score >= 40:
        kinds |= {"save", "view_photo", "view_review"}
    if score >= 60:
        kinds |= {"vote", "follow"}
    if score >= REVIEW_THRESHOLD:
        kinds |= {"review", "checkin"}
    return kinds


def review_eligible(account_id: uuid.UUID, *, now: datetime | None = None) -> tuple[bool, str]:
    from db.models import WarmingSession

    now = now or datetime.now(timezone.utc)
    breakdown = compute_trust(account_id, now=now)
    if breakdown.score < REVIEW_THRESHOLD:
        evidence = warm_evidence(account_id, now=now)
        return False, (
            f"trust {breakdown.score} < {REVIEW_THRESHOLD} "
            f"(warm {breakdown.warm:.1f}/30, sessions {evidence.sessions}, days {evidence.active_days})"
        )
    with session_scope() as session:
        account = session.get(Account, account_id)
        if account is None or account.created_at is None:
            return False, "no_account"
        age_days = (now - account.created_at).days
        sessions = session.scalar(
            select(func.count(WarmingSession.id)).where(
                WarmingSession.account_id == account_id,
                WarmingSession.started_at >= now - timedelta(days=7),
            )
        )
        filtered = session.scalars(
            select(ReviewAttempt).where(
                ReviewAttempt.account_id == account_id,
                ReviewAttempt.filtered_at.isnot(None),
                ReviewAttempt.filtered_at >= now - timedelta(days=7),
            )
        ).first()
    if age_days < REVIEW_MIN_AGE_DAYS:
        return False, f"age {age_days}d < {REVIEW_MIN_AGE_DAYS}"
    if (sessions or 0) < REVIEW_MIN_SESSIONS_7D:
        return False, f"sessions_7d {sessions} < {REVIEW_MIN_SESSIONS_7D}"
    if filtered is not None:
        return False, "recent_filtered_review"
    return True, "ok"
