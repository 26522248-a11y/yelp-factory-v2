"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-04

Explicit DDL for the schema as of this revision.

Why not ``Base.metadata.create_all()``: that builds the *current* model schema, so
``0002`` (``add_column accounts.gender``) always died with
``DuplicateColumn: column "gender" of relation "accounts" already exists`` and the chain
could never be replayed on a fresh database. Every revision must therefore describe the
schema *of its own point in time*; later revisions add the rest.

Tables here: profiles, proxies, accounts, runs, steps, events, warming_plans,
warming_tasks, selector_registry, quarantine, gpm_operations, account_locks, zips,
email_domains, sms_numbers. Everything else is created by 0004/0005/0006/0008/0011.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proxies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("raw", sa.Text(), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("zip_prefixes", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("health", sa.String(16), nullable=False),
        sa.Column("fail_streak", sa.Integer(), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("gpm_profile_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("proxy_id", sa.Uuid(), sa.ForeignKey("proxies.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fingerprint_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("profile_id", sa.Uuid(), sa.ForeignKey("profiles.id"), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("email_password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("email_alias", sa.String(320), nullable=True),
        sa.Column("phone_e164", sa.String(32), nullable=True),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=False),
        sa.Column("zip", sa.String(16), nullable=False),
        sa.Column("city", sa.String(160), nullable=False),
        sa.Column("password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("yelp_user_id", sa.String(120), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("substate", sa.String(64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quarantine_reason", sa.String(64), nullable=True),
        sa.UniqueConstraint("profile_id", name="uq_accounts_profile_id"),
        sa.UniqueConstraint("email", name="uq_accounts_email"),
    )
    op.create_index("ix_accounts_state", "accounts", ["state"])
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
    )
    # Mỗi account tối đa 1 run RUNNING (E-26: dispatch trùng thì worker 2 exit sạch).
    op.create_index(
        "uq_runs_one_running_per_account",
        "runs",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("state = 'RUNNING'"),
    )
    op.create_table(
        "steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("artifact_prefix", sa.String(400), nullable=True),
        sa.UniqueConstraint("run_id", "seq", name="uq_steps_run_seq"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(16), nullable=True),
        sa.Column("msg", sa.Text(), nullable=False),
        sa.Column("ctx", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_events_ts", "events", ["ts"])
    op.create_index("ix_events_code", "events", ["code"])
    op.create_table(
        "warming_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("phase", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("budget", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
    )
    op.create_table(
        "warming_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("warming_plans.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_warming_tasks_due", "warming_tasks", ["due_at", "status"])
    op.create_table(
        "selector_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("strategy", sa.String(24), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("page_tag", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("miss_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("key", "strategy", "value", name="uq_selector_unique"),
    )
    op.create_index("ix_selector_registry_key", "selector_registry", ["key"])
    op.create_table(
        "quarantine",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "gpm_operations",
        sa.Column("operation_id", sa.String(120), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("gpm_profile_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "account_locks",
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("worker_id", sa.String(120), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
    )
    op.create_table(
        "zips",
        sa.Column("zip", sa.String(16), primary_key=True),
        sa.Column("city", sa.String(160), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("yelp_served", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "email_domains",
        sa.Column("domain", sa.String(255), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("fail_streak", sa.Integer(), nullable=False),
        sa.Column("disabled_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "sms_numbers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("e164", sa.String(32), nullable=False, unique=True),
        sa.Column("area_code", sa.String(8), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("used_by_account", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sms_numbers")
    op.drop_table("email_domains")
    op.drop_table("zips")
    op.drop_table("account_locks")
    op.drop_table("gpm_operations")
    op.drop_table("quarantine")
    op.drop_index("ix_selector_registry_key", table_name="selector_registry")
    op.drop_table("selector_registry")
    op.drop_index("ix_warming_tasks_due", table_name="warming_tasks")
    op.drop_table("warming_tasks")
    op.drop_table("warming_plans")
    op.drop_index("ix_events_code", table_name="events")
    op.drop_index("ix_events_ts", table_name="events")
    op.drop_table("events")
    op.drop_table("steps")
    op.drop_index("uq_runs_one_running_per_account", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_accounts_state", table_name="accounts")
    op.drop_table("accounts")
    # profiles.proxy_id -> proxies.id: drop profiles first or downgrade base dies
    # with DependentObjectsStillExist (found by replaying the chain).
    op.drop_table("profiles")
    op.drop_table("proxies")
