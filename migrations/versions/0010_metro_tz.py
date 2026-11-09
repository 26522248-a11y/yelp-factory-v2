"""metro timezone for local scheduling windows

Revision ID: 0010_metro_tz
Revises: 0009_probe
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_metro_tz"
down_revision = "0009_probe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "metros",
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/New_York"),
    )
    op.execute("UPDATE metros SET timezone = 'America/New_York' WHERE name ILIKE '%New York%'")
    op.execute("UPDATE metros SET timezone = 'America/Los_Angeles' WHERE name ILIKE '%Los Angeles%' OR name ILIKE '%San Francisco%'")
    op.execute("UPDATE metros SET timezone = 'America/Chicago' WHERE name ILIKE '%Chicago%' OR name ILIKE '%Dallas%' OR name ILIKE '%Austin%' OR name ILIKE '%Houston%'")
    op.execute("UPDATE metros SET timezone = 'America/Denver' WHERE name ILIKE '%Denver%' OR name ILIKE '%Phoenix%'")


def downgrade() -> None:
    op.drop_column("metros", "timezone")
