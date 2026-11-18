"""multi-machine node registry

Adds the ``nodes`` table used by the console Nodes screen: each machine posts a
heartbeat (console or worker) and the console marks a node offline after 120s.

Revision ID: 0014_nodes
Revises: 0013_account_lifecycle
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_nodes"
down_revision = "0013_account_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("hostname", sa.String(200), nullable=False, server_default=""),
        sa.Column("role", sa.String(32), nullable=False, server_default="console"),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="online"),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_nodes_last_seen", "nodes", ["last_seen"])


def downgrade() -> None:
    op.drop_index("ix_nodes_last_seen", table_name="nodes")
    op.drop_table("nodes")
