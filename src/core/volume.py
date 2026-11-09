"""Volume governor: lazy weeks, filter-rate throttle, time-of-day pacing (2026-11-09).

Every operation that creates review work multiplies the daily allowance by
``effective_multiplier()``:
* lazy weeks: 2 of every 4 weeks run at 60% volume (people have slow weeks);
* filter-rate throttle: system filter rate > 35% -> 70% volume;
* manual pin: ``system_flags.volume`` {"multiplier": x} overrides everything.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from core.flags import get_flag
from obs.log import get_logger

log = get_logger("volume")

LAZY_WEEKS_PER_MONTH = 2
LAZY_MULTIPLIER = 0.6
FILTER_THROTTLE_RATE = 0.35
FILTER_THROTTLE_MULTIPLIER = 0.7


def iso_week(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    return int(now.strftime("%V"))


def is_lazy_week(now: datetime | None = None) -> bool:
    """Deterministic per ISO week: 2 of every 4 weeks are slow weeks."""
    week = iso_week(now)
    return week % 4 in (0, 2)


def filter_rate_7d() -> float:
    """Share of assignments published in the last 7 days that Yelp filtered."""
    from db.models import Assignment
    from db.session import session_scope

    since = datetime.now(timezone.utc) - timedelta(days=7)
    with session_scope() as session:
        rows = (
            session.query(Assignment.filtered_at)
            .filter(Assignment.published_at.is_not(None), Assignment.published_at >= since)
            .all()
        )
    if not rows:
        return 0.0
    filtered = sum(1 for (value,) in rows if value is not None)
    return filtered / len(rows)


def effective_multiplier(now: datetime | None = None) -> float:
    pinned = get_flag("volume", {})
    if pinned.get("paused"):
        return 0.0
    if "multiplier" in pinned:
        return max(0.0, float(pinned["multiplier"]))
    multiplier = 1.0
    if is_lazy_week(now):
        multiplier *= LAZY_MULTIPLIER
    if filter_rate_7d() > FILTER_THROTTLE_RATE:
        multiplier *= FILTER_THROTTLE_MULTIPLIER
        log.warning("volume_filter_throttle", rate=round(filter_rate_7d(), 3))
    return multiplier


# --------------------------------------------------------------------------------------
# time-of-day pacing: 30% morning / 40% afternoon / 30% evening
# --------------------------------------------------------------------------------------

MORNING = (8, 11)
AFTERNOON = (12, 17)
EVENING = (17, 20)


def pick_slot_hour(rng: random.Random | None = None) -> int:
    rng = rng or random
    band = rng.choices([MORNING, AFTERNOON, EVENING], weights=[30, 40, 30], k=1)[0]
    return rng.randint(band[0], band[1])


def next_due_at(now: datetime | None = None, *, min_gap_days: int = 5) -> datetime:
    """A future posting time inside the daily window, with the requested gap."""
    rng = random.Random()
    now = now or datetime.now().astimezone()
    day = now.date() + timedelta(days=min_gap_days)
    return datetime.combine(day, datetime.min.time()).replace(hour=pick_slot_hour(rng)).astimezone()
