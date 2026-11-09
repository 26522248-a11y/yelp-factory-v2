"""email/proxy pools

Revision ID: 0005_pools
Revises: 0004_warming_trust
Create Date: 2026-11-04

Explicit DDL, and the functional unique index on ``lower(mailbox_email)`` is declared
here because it exists from this revision on (declaring it only in 0012 left fresh
installs without the index - Alembic autogenerate does not reliably diff expression
indexes, alembic issue #428). 0012 keeps its data-collapse step and its
``create_index`` is guarded so the replay stays idempotent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_pools"
down_revision = "0004_warming_trust"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_email_pool_mailbox_email_lower"


def _index_exists() -> bool:
    """0012.downgrade() may already have dropped it, so the replay must tolerate absence."""
    bind = op.get_bind()
    return bind.execute(
        sa.text("select 1 from pg_indexes where schemaname = 'public' and indexname = :n"),
        {"n": INDEX_NAME},
    ).first() is not None


def upgrade() -> None:
    op.create_table(
        "email_pool",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mailbox_email", sa.String(320), nullable=False, unique=True),
        sa.Column("mailbox_password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("client_id", sa.String(120), nullable=False),
        sa.Column("alias", sa.String(320), nullable=False, unique=True),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("source_file", sa.String(300), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reserved_by", sa.Uuid(), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_email_pool_mailbox_email_lower",
        "email_pool",
        [sa.text("lower(mailbox_email)")],
        unique=True,
    )
    op.create_table(
        "proxy_pool",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("raw", sa.Text(), nullable=False, unique=True),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("accounts_count", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_file", sa.String(300), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reserved_by", sa.Uuid(), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("accounts", sa.Column("email_pool_id", sa.Uuid(), nullable=True))
    op.add_column("accounts", sa.Column("proxy_pool_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("accounts_email_pool_id_fkey", "accounts", "email_pool", ["email_pool_id"], ["id"])
    op.create_foreign_key("accounts_proxy_pool_id_fkey", "accounts", "proxy_pool", ["proxy_pool_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("accounts_proxy_pool_id_fkey", "accounts", type_="foreignkey")
    op.drop_constraint("accounts_email_pool_id_fkey", "accounts", type_="foreignkey")
    op.drop_column("accounts", "proxy_pool_id")
    op.drop_column("accounts", "email_pool_id")
    op.drop_table("proxy_pool")
    if _index_exists():
        op.drop_index(INDEX_NAME, table_name="email_pool")
    op.drop_table("email_pool")
