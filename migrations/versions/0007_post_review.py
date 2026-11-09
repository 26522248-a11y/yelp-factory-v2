"""post-review warm mode

Revision ID: 0007_post_review
Revises: 0006_batches
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_post_review"
down_revision = "0006_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("warming_sessions", sa.Column("mode", sa.String(32), nullable=False, server_default="warm"))
    op.add_column("warming_sessions", sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("accounts", sa.Column("reviews_done", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("accounts", "reviews_done")
    op.drop_column("warming_sessions", "meta")
    op.drop_column("warming_sessions", "mode")
