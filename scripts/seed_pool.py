"""Seed live GPMLogin profiles into the factory DB (one-off adoption).

Credentials are NOT stored in this file. They are read from a JSON file outside
version control (default: data/seed_accounts.json - `data/` is gitignored;
schema: docs/seed_accounts.example.json). Override the path with
YF_SEED_ACCOUNTS, the metro with YF_SEED_METRO.

Creates metros, profiles, accounts (READY, profile_complete), a trust snapshot and
the six warming sessions that review eligibility expects. Idempotent by email.
"""

from __future__ import annotations

import json
import os
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

METRO = os.environ.get("YF_SEED_METRO", "New York, NY")
SEED_FILE = Path(os.environ.get("YF_SEED_ACCOUNTS", str(ROOT / "data" / "seed_accounts.json")))
REQUIRED_FIELDS = (
    "email",
    "password",
    "gpm",
    "first",
    "last",
    "zip",
    "city",
    "user_id",
    "profile_name",
)


def load_accounts(path: Path = SEED_FILE) -> list[dict]:
    """Load account specs from a gitignored JSON file (never from source code)."""
    if not path.exists():
        raise SystemExit(
            f"missing seed file: {path}\n"
            "copy docs/seed_accounts.example.json to data/seed_accounts.json and fill in "
            "real values (data/ is gitignored, the file must never be committed)"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    accounts = raw["accounts"] if isinstance(raw, dict) else raw
    if not isinstance(accounts, list) or not accounts:
        raise SystemExit(f"{path}: expected a non-empty list under 'accounts'")
    for spec in accounts:
        missing = [field for field in REQUIRED_FIELDS if not spec.get(field)]
        if missing:
            raise SystemExit(f"{path}: account {spec.get('email', '<no email>')} missing {missing}")
    return accounts


def main() -> int:
    accounts = load_accounts()
    metro_id = ensure_metro(METRO)
    box = SecretBox()
    now = datetime.now(timezone.utc)
    created = 0
    for spec in accounts:
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
