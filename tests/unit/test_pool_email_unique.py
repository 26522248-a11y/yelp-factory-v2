"""mailbox_email uniqueness must be case-insensitive (spec v1.1, pool import).

Regression: the column-level UNIQUE on ``email_pool.mailbox_email`` compares bytes, so
importing ``Bob@Gmail.com`` after ``bob@gmail.com`` created a second row and the same
inbox could be reserved for two accounts (one account per mailbox is a hard rule).
"""

from __future__ import annotations

import uuid

import pytest

from core.importers import ParsedEmail, parse_emails
from core.pool import import_emails, reserve_email
from db.models import EmailPool
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready", "isolate_pool", "clean_pool")

TOKEN = "M.C524." + "x" * 40


def _email(mailbox: str, alias: str) -> ParsedEmail:
    return ParsedEmail(
        mailbox_email=mailbox,
        mailbox_password="pw",
        refresh_token=TOKEN,
        client_id="client",
        alias=alias,
    )


def test_reimport_same_mailbox_different_case_is_rejected():
    tag = uuid.uuid4().hex[:8]
    first = import_emails([_email(f"Bob{tag}@Gmail.com", f"bob{tag}@fviainboxes.com")])
    assert first["inserted"] == 1

    second = import_emails([_email(f"bob{tag}@gmail.com", f"bob2{tag}@fviainboxes.com")])
    assert second["inserted"] == 0
    assert second["duplicates_in_db"] == 1

    with session_scope() as session:
        rows = session.query(EmailPool).filter(EmailPool.alias == f"bob2{tag}@fviainboxes.com").all()
    assert rows == []


def test_duplicate_row_does_not_abort_the_rest_of_the_batch():
    tag = uuid.uuid4().hex[:8]
    import_emails([_email(f"dup{tag}@Gmail.com", f"dup{tag}@fviainboxes.com")])
    report = import_emails(
        [
            _email(f"DUP{tag}@gmail.com", f"dup2{tag}@fviainboxes.com"),
            _email(f"fresh{tag}@gmail.com", f"fresh{tag}@fviainboxes.com"),
        ]
    )
    assert report == {"inserted": 1, "duplicates_in_db": 1}
    with session_scope() as session:
        assert session.query(EmailPool).filter(EmailPool.alias == f"fresh{tag}@fviainboxes.com").count() == 1


def test_reserve_never_hands_out_the_same_inbox_twice():
    tag = uuid.uuid4().hex[:8]
    import_emails([_email(f"one{tag}@Gmail.com", f"one{tag}@fviainboxes.com")])
    import_emails([_email(f"ONE{tag}@gmail.com", f"one2{tag}@fviainboxes.com")])

    first = reserve_email(uuid.uuid4())
    second = reserve_email(uuid.uuid4())
    assert first is not None
    assert second is None  # only one row exists for that inbox
    assert first.mailbox_email.lower() == f"one{tag}@gmail.com"


def test_lower_unique_index_exists_in_database():
    """db-check cannot see functional indexes (alembic autogenerate blind spot),
    so assert the index really exists in pg_indexes."""
    from sqlalchemy import text as sa_text

    with session_scope() as session:
        rows = session.execute(
            sa_text(
                "select indexdef from pg_indexes "
                "where tablename = 'email_pool' and indexname = 'uq_email_pool_mailbox_email_lower'"
            )
        ).all()
    assert len(rows) == 1
    indexdef = rows[0][0].lower()
    assert "unique index" in indexdef
    assert "lower(" in indexdef
    assert "mailbox_email" in indexdef


def test_parse_dedupe_is_case_insensitive():
    tag = uuid.uuid4().hex[:8]
    line = f"Case{tag}@gmail.com|pw|{TOKEN}|client|case{tag}@fviainboxes.com"
    text = line + "\n" + line.replace(f"Case{tag}@gmail.com", f"case{tag}@GMAIL.com")
    report = parse_emails(text, default_client_id="client", default_domain="fviainboxes.com")
    assert len(report.rows) == 1
    assert report.duplicates == 1
