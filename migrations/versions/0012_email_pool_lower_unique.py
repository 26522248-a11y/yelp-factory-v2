"""email_pool: unique mailbox_email case-insensitively

The column-level UNIQUE on ``mailbox_email`` is case-sensitive, so importing the same
mailbox twice with different casing (``Bob@Gmail.com`` vs ``bob@gmail.com``) created two
pool rows and the same inbox could be handed to two accounts. This revision collapses
existing case-duplicates and adds a functional unique index on ``lower(mailbox_email)``.

Revision ID: 0012_email_pool_lower_unique
Revises: 0011_slots
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_email_pool_lower_unique"

down_revision = "0011_slots"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_email_pool_mailbox_email_lower"


def _index_exists() -> bool:
    """0005 already declares this index (fresh installs get it from there), so the
    replay must not create it twice."""
    bind = op.get_bind()
    found = bind.execute(
        sa.text("select 1 from pg_indexes where schemaname = 'public' and indexname = :n"),
        {"n": INDEX_NAME},
    ).first()
    return found is not None


def upgrade() -> None:
    # Collapse case-duplicates first, otherwise the unique index cannot be built.
    # Keep the row an account is already bound to, otherwise the oldest one; a duplicate
    # that is still referenced by an account aborts the migration (FK) instead of being
    # silently dropped - losing mailbox credentials is worse than a failed deploy.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY lower(mailbox_email)
                    ORDER BY (
                        SELECT count(*) FROM accounts a WHERE a.email_pool_id = email_pool.id
                    ) DESC,
                    imported_at NULLS LAST,
                    id
                ) AS rn
            FROM email_pool
        )
        DELETE FROM email_pool WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
    if not _index_exists():
        op.create_index(
            INDEX_NAME,
            "email_pool",
            [sa.text("lower(mailbox_email)")],
            unique=True,
        )


def downgrade() -> None:
    if _index_exists():
        op.drop_index(INDEX_NAME, table_name="email_pool")
