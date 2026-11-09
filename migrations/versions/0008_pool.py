"""account pool: metros, clients, assignments, system flags, lifecycle columns

Revision ID: 0008_pool
Revises: 0007_post_review
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_pool"
down_revision = "0007_post_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metros",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("state", sa.String(8), nullable=False, server_default=""),
        sa.Column("country", sa.String(2), nullable=False, server_default="US"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("business_name", sa.String(200), nullable=False),
        sa.Column("metro_id", sa.Uuid(), sa.ForeignKey("metros.id"), nullable=True),
        sa.Column("category", sa.String(64), nullable=False, server_default="other"),
        sa.Column("yelp_biz_id", sa.String(200), nullable=False, unique=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("facts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filtered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "account_id", name="uq_assignment_client_account"),
    )
    op.create_index("ix_assignment_due", "assignments", ["status", "review_due_at"])
    op.create_table(
        "system_flags",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("accounts", sa.Column("metro_id", sa.Uuid(), sa.ForeignKey("metros.id"), nullable=True))
    op.create_index("ix_accounts_metro", "accounts", ["metro_id"])
    op.add_column("accounts", sa.Column("profile_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("proxies", sa.Column("asn", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("proxies", "asn")
    op.drop_column("accounts", "profile_complete")
    op.drop_index("ix_accounts_metro", table_name="accounts")
    op.drop_column("accounts", "metro_id")
    op.drop_table("system_flags")
    op.drop_index("ix_assignment_due", table_name="assignments")
    op.drop_table("assignments")
    op.drop_table("clients")
    op.drop_table("metros")
