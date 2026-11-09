"""account last_probe_at for the 3-day session health probe

Revision ID: 0009_probe
Revises: 0008_pool
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_probe"
down_revision = "0008_pool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "last_probe_at")
