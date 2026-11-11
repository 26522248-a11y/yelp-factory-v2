"""account lifecycle fields for the adopt -> profile -> seed -> gate flow

Adds the columns the B-K SOP needs on ``accounts``:
supplier/home_city/city_changed_at/use_count/tier/friend_count/tip_count/
checkin_count/seed_review_*_at/last_filtered_at/blacklisted/adopted_at.

``home_city`` is the account's original city and is deliberately separate from
``metro_id`` (the client's target metro): the 48h city-change lock compares
``city_changed_at`` with the review time, so the two must never be one column.
Existing rows are backfilled with ``home_city = city`` (blank city becomes NULL, never
an empty string) and ``use_count = 0``. ``tier`` is ``String(8)`` so the gate can store
the Vietnamese verdict ``'Loại'`` next to ``A/B/C``; ``NULL`` means "not scored yet".

DOWNGRADE IS LOSSY BY DESIGN: ``downgrade()`` drops all 14 columns, so a
``downgrade 0012`` followed by ``upgrade head`` keeps the ``accounts`` rows and their
ids but resets every lifecycle value to its default (``tier``/``home_city``/
``adopted_at``/``seed_review_*_at``/``last_filtered_at`` = NULL, counts = 0,
``blacklisted`` = false; ``home_city`` is re-derived from ``city`` by the backfill).
Nobody should keep state across that cycle and the migration must not try to:
``alembic check`` + constraints after the re-upgrade are the contract
(see ``data/_p0_updown.py``). Because the downgrade is lossy, a **backup is
mandatory before running this on production** (``yelp_factory`` is still at 0012),
and the rollback path is "restore the backup", not "downgrade".

Revision ID: 0013_account_lifecycle
Revises: 0012_email_pool_lower_unique
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_account_lifecycle"
down_revision = "0012_email_pool_lower_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("supplier", sa.String(64), nullable=True))
    op.add_column("accounts", sa.Column("home_city", sa.String(160), nullable=True))
    op.add_column("accounts", sa.Column("city_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("accounts", sa.Column("tier", sa.String(8), nullable=True))
    op.add_column("accounts", sa.Column("friend_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("accounts", sa.Column("tip_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("accounts", sa.Column("checkin_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("accounts", sa.Column("seed_review_1_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("seed_review_2_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("seed_review_3_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("last_filtered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounts", sa.Column("blacklisted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("accounts", sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True))

    # Existing accounts are legacy signups: their current city *is* the home city.
    # btrim + NULLIF: a blank legacy city must not become home_city='' (gate condition 3
    # would then never match and the account would fail silently much later).
    op.execute("UPDATE accounts SET home_city = NULLIF(btrim(city), '') WHERE home_city IS NULL")

    op.create_check_constraint("ck_accounts_use_count_range", "accounts", "use_count BETWEEN 0 AND 4")
    op.create_check_constraint(
        "ck_accounts_counts_non_negative",
        "accounts",
        "friend_count >= 0 AND tip_count >= 0 AND checkin_count >= 0",
    )
    # '' is not "unknown": adopt rejects a blank home city and NULL is the only unknown.
    op.create_check_constraint(
        "ck_accounts_home_city_not_blank",
        "accounts",
        "home_city IS NULL OR btrim(home_city) <> ''",
    )
    op.create_check_constraint(
        "ck_accounts_tier_enum",
        "accounts",
        "tier IS NULL OR tier IN ('A', 'B', 'C', 'Loại')",
    )
    op.create_index("ix_accounts_supplier", "accounts", ["supplier"])
    op.create_index("ix_accounts_tier", "accounts", ["tier"])
    op.create_index("ix_accounts_blacklisted", "accounts", ["blacklisted"])


def downgrade() -> None:
    op.drop_index("ix_accounts_blacklisted", table_name="accounts")
    op.drop_index("ix_accounts_tier", table_name="accounts")
    op.drop_index("ix_accounts_supplier", table_name="accounts")
    # IF EXISTS: a database stamped with an older 0013 (before home_city was added) has
    # fewer constraints, and an unconditional drop then fails the whole downgrade.
    for name in (
        "ck_accounts_tier_enum",
        "ck_accounts_home_city_not_blank",
        "ck_accounts_counts_non_negative",
        "ck_accounts_use_count_range",
    ):
        op.execute(f"ALTER TABLE accounts DROP CONSTRAINT IF EXISTS {name}")
    for column in (
        "adopted_at",
        "blacklisted",
        "last_filtered_at",
        "seed_review_3_at",
        "seed_review_2_at",
        "seed_review_1_at",
        "checkin_count",
        "tip_count",
        "friend_count",
        "tier",
        "use_count",
        "city_changed_at",
        "home_city",
        "supplier",
    ):
        op.drop_column("accounts", column)
