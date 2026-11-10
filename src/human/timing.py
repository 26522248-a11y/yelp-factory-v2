"""Session rhythm helpers: working hours, session length, idle jitter (section 8.1)."""

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, time

# US city -> IANA timezone for the working-hours window
CITY_TIMEZONES = {
    "Austin, TX": "America/Chicago",
    "Dallas, TX": "America/Chicago",
    "Houston, TX": "America/Chicago",
    "Miami, FL": "America/New_York",
    "Delray Beach, FL": "America/New_York",
    "Boca Raton, FL": "America/New_York",
    "Tampa, FL": "America/New_York",
    "Orlando, FL": "America/New_York",
    "Jacksonville, FL": "America/New_York",
    "Seattle, WA": "America/Los_Angeles",
    "Portland, OR": "America/Los_Angeles",
    "Los Angeles, CA": "America/Los_Angeles",
    "San Diego, CA": "America/Los_Angeles",
    "San Francisco, CA": "America/Los_Angeles",
    "Las Vegas, NV": "America/Los_Angeles",
    "Phoenix, AZ": "America/Phoenix",
    "Denver, CO": "America/Denver",
    "Salt Lake City, UT": "America/Denver",
    "Overland Park, KS": "America/Chicago",
    "Kansas City, MO": "America/Chicago",
    "Little Rock, AR": "America/Chicago",
    "Fort Smith, AR": "America/Chicago",
    "Chicago, IL": "America/Chicago",
    "Minneapolis, MN": "America/Chicago",
    "Milwaukee, WI": "America/Chicago",
    "New Orleans, LA": "America/Chicago",
    "Oklahoma City, OK": "America/Chicago",
    "Nashville, TN": "America/Chicago",
    "New York, NY": "America/New_York",
    "Atlanta, GA": "America/New_York",
    "Charlotte, NC": "America/New_York",
    "Columbus, OH": "America/New_York",
    "Cleveland, OH": "America/New_York",
    "Philadelphia, PA": "America/New_York",
    "Detroit, MI": "America/New_York",
    "Richmond, VA": "America/New_York",
    "Boston, MA": "America/New_York",
    "Newark, NJ": "America/New_York",
    "Baltimore, MD": "America/New_York",
    "Indianapolis, IN": "America/Indiana/Indianapolis",
    "Louisville, KY": "America/Kentucky/Louisville",
}

WORK_START = time(6, 0)
WORK_END = time(23, 0)


def local_now(city: str) -> datetime:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(CITY_TIMEZONES.get(city, "America/Chicago"))
    return datetime.now(tz)


def within_working_hours(city: str) -> bool:
    now = local_now(city).time()
    return WORK_START <= now <= WORK_END


def session_length_seconds() -> int:
    return random.randint(4 * 60, 12 * 60)


def empty_session(probability: float = 0.05) -> bool:
    """SHOULD: ~5% of sessions only open the site to break the pattern."""
    return random.random() < probability


def _human_time_scale() -> float:
    """Multiplier applied to all human timing (sleep/idle/dwell).

    Default 1.0 keeps the production cadence. 0.0 collapses waits during tests.
    Read on every call so tests can override via environment without reloads.
    """
    raw = os.environ.get("YF_HUMAN_TIME_SCALE", "1.0")
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _scaled_delay(raw_seconds: float) -> float:
    scale = _human_time_scale()
    if scale <= 0.0:
        return 0.0
    return raw_seconds * scale


async def idle(page, low: float = 0.8, high: float = 3.0) -> None:
    await page.wait_for_timeout(int(_scaled_delay(random.uniform(low, high)) * 1000))


async def sleep_s(seconds: float) -> None:
    """Drop-in async sleep that respects YF_HUMAN_TIME_SCALE."""
    await asyncio.sleep(_scaled_delay(seconds))
