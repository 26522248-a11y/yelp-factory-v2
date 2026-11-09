"""Seed the 4 live GPMLogin profiles into the factory DB (one-off adoption).

Creates metros, profiles, accounts (READY, profile_complete), a trust snapshot and
the six warming sessions that review eligibility expects. Idempotent by email.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.clients import ensure_metro  # noqa: E402
from core.crypto import SecretBox  # noqa: E402
from db.models import Account, AccountState, Profile, TrustScore, WarmingSession  # noqa: E402
from db.session import session_scope  # noqa: E402

METRO = "New York, NY"

ACCOUNTS = [
    {
        "email": "benita198617nellie966cyjpvk@outlook.com",
        "password": "c8DeborahueA63tk",
        "first": "Betty", "last": "M.", "zip": "10001", "city": "Manhattan, NY",
        "user_id": "tu5rZ7CTBpe6oTZNowzWsg",
        "gpm": "4c2b5b3c-8c63-4445-80f7-901709433f4c",
        "profile_name": "Resi US - sess 0486848620",
    },
    {
        "email": "patricialopezsteven924ebtsthxq@outlook.com",
        "password": "r3LauraoiU34vk",
        "first": "Jennifer", "last": "B.", "zip": "11201", "city": "Brooklyn, NY",
        "user_id": "KEdVZKG-MSXbRTxvuvabjA",
        "gpm": "bf35df54-afa8-4fc7-a3ee-6cac8541266e",
        "profile_name": "Mobile CA - sess 0496821249",
    },
    {
        "email": "cassie199115heidi722w0cz2w@outlook.com",
        "password": "a1SharonoaU92ee",
        "first": "Thomas", "last": "E.", "zip": "11101", "city": "Queens, NY",
        "user_id": "IfPWol9uBd4CsEZfACGjBg",
        "gpm": "618de509-6ad4-41bb-9f27-112ba77959e1",
        "profile_name": "Mobile US - sess 0496579219",
    },
    {
        "email": "helenwrightrichard712ulzr4o34@outlook.com",
        "password": "h0ElizabethoaU65td",
        "first": "David", "last": "J.", "zip": "10451", "city": "Bronx, NY",
        "user_id": "anfLEXysAQlqZKfZcH321w",
        "gpm": "7b6aae75-9d7c-4f5b-95dd-fb70d984bb51",
        "profile_name": "Mobile US - sess 0053315574",
    },
]


def main() -> int:
    metro_id = ensure_metro(METRO)
    box = SecretBox()
    now = datetime.now(timezone.utc)
    created = 0
    for spec in ACCOUNTS:
        with session_scope() as session:
            existing = session.query(Account).filter(Account.email == spec["email"]).one_or_none()
            if existing is not None:
                print(f"skip (exists): {spec['email']}")
                continue
            profile = Profile(
                gpm_profile_id=spec["gpm"],
                name=spec["profile_name"],
                status="ready",
                fingerprint_json={},
            )
            session.add(profile)
            session.flush()
            account = Account(
                id=uuid.uuid4(),
                profile_id=profile.id,
                email=spec["email"],
                email_alias=spec["email"],
                first_name=spec["first"],
                last_name=spec["last"],
                zip=spec["zip"],
                city=spec["city"],
                password_enc=box.encrypt(spec["password"]),
                yelp_user_id=spec["user_id"],
                state=AccountState.READY.value,
                reviews_done=True,
                profile_complete=True,
                metro_id=metro_id,
                created_at=now - timedelta(days=14),
                activated_at=now - timedelta(days=14),
            )
            session.add(account)
            session.flush()
            # No seeded trust: trust is derived from real action/review history, and the
            # planner recomputes it live (a stored number must never open the gate).
            for index in range(6):
                session.add(
                    WarmingSession(
                        account_id=account.id,
                        mode="post_review",
                        started_at=now - timedelta(days=index % 5, hours=index + 1),
                        ended_at=now - timedelta(days=index % 5, hours=index),
                        actions=20,
                        entry_path="ladder",
                        meta={"seed": True},
                    )
                )
            created += 1
            print(f"created: {spec['email']}")
    print(f"done: {created} created, metro={METRO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
