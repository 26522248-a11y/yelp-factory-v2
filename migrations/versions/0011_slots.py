"""browser concurrency slots

Revision ID: 0011_slots
Revises: 0010_metro_tz
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_slots"
down_revision = "0010_metro_tz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_slots",
        sa.Column("token", sa.Uuid(), primary_key=True),
        sa.Column("worker_id", sa.String(120), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="warm"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="7200"),
    )


def downgrade() -> None:
    op.drop_table("browser_slots")
