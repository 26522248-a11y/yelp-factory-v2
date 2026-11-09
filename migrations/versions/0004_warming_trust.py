"""warming trust tables

Revision ID: 0004_warming_trust
Revises: 0003_proxy_ip
Create Date: 2026-11-04

Explicit DDL (schema *as of this revision*), not ``Model.__table__.create()``: importing
the live models here would create today's columns (``warming_sessions.mode``/``meta``),
which 0007 then tries to add again and the replay dies.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_warming_trust"
down_revision = "0003_proxy_ip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trust_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_trust_account_ts", "trust_scores", ["account_id", "ts"])
    op.create_table(
        "action_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("target", sa.String(300), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_action_account_ts", "action_log", ["account_id", "ts"])
    op.create_table(
        "warming_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actions", sa.Integer(), nullable=False),
        sa.Column("entry_path", sa.String(32), nullable=True),
        sa.Column("proxy_ip", sa.String(64), nullable=True),
        sa.Column("trust_before", sa.Integer(), nullable=True),
        sa.Column("trust_after", sa.Integer(), nullable=True),
    )
    op.create_table(
        "review_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("business_id", sa.String(200), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("words", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("photo", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filtered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_review_account_biz", "review_attempts", ["account_id", "business_id"])


def downgrade() -> None:
    op.drop_index("ix_review_account_biz", table_name="review_attempts")
    op.drop_table("review_attempts")
    op.drop_table("warming_sessions")
    op.drop_index("ix_action_account_ts", table_name="action_log")
    op.drop_table("action_log")
    op.drop_index("ix_trust_account_ts", table_name="trust_scores")
    op.drop_table("trust_scores")
