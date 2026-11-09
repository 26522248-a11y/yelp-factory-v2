"""batch tracking

Revision ID: 0006_batches
Revises: 0005_pools
Create Date: 2026-11-05

Explicit DDL instead of ``Batch.__table__.create()`` so the replay builds the schema of
*this* revision and later ones add their own columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_batches"
down_revision = "0005_pools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False, unique=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(400), nullable=True),
    )
    op.add_column("accounts", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("accounts_batch_id_fkey", "accounts", "batches", ["batch_id"], ["id"])
    op.create_index("ix_accounts_batch_id", "accounts", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_accounts_batch_id", table_name="accounts")
    op.drop_constraint("accounts_batch_id_fkey", "accounts", type_="foreignkey")
    op.drop_column("accounts", "batch_id")
    op.drop_table("batches")
