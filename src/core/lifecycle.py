"""Account lifecycle rules shared by adopt, the gate and the review path (spec B-K).

The only stateful rule here is the 48h city-change lock: after an adopted account is
moved to the client's metro it must keep browsing before it may publish a review. The
lock lives in one place so the CLI, the gate and ``run_due_reviews`` cannot disagree.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

CITY_CHANGE_LOCK = timedelta(hours=48)

# NULL = not scored yet, 'Loại' = failed the gate. blacklisted is the permanent drop.
TIERS = (None, "A", "B", "C", "Loại")
USABLE_TIERS = ("A", "B", "C")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def city_lock_until(account, *, now: datetime | None = None) -> datetime | None:
    """End of the 48h lock, or ``None`` when the account may review now."""
    changed_at = getattr(account, "city_changed_at", None)
    if changed_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    until = _aware(changed_at) + CITY_CHANGE_LOCK
    return until if until > now else None


def city_change_locked(account, *, now: datetime | None = None) -> bool:
    return city_lock_until(account, now=now) is not None


def review_block_reason(account, *, now: datetime | None = None) -> str | None:
    """Machine-readable reason the lifecycle forbids a review right now, if any."""
    if getattr(account, "blacklisted", False):
        return "blacklisted"
    if getattr(account, "tier", None) == "Loại":
        return "tier_loai"
    until = city_lock_until(account, now=now)
    if until is not None:
        return f"city_change_lock_until:{until.isoformat()}"
    return None
