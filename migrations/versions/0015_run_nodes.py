"""node attribution for runs and browser slots

Lets the Nodes screen show which machine is running what: every run and browser
slot now records the engine/worker node that owns it.

Revision ID: 0015_run_nodes
Revises: 0014_nodes
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_run_nodes"
down_revision = "0014_nodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("node_id", sa.String(120), nullable=True))
    op.create_index("ix_runs_node", "runs", ["node_id"])
    op.add_column("browser_slots", sa.Column("node_id", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("browser_slots", "node_id")
    op.drop_index("ix_runs_node", table_name="runs")
    op.drop_column("runs", "node_id")
