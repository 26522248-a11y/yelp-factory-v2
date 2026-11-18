"""Unit tests for the console account projection (no database required)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.accounts_api import (
    AccountFilters,
    account_payload,
    get_account,
    list_accounts,
    parse_filters,
)


def make_account(**overrides) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(),
        email="amelia.hart@example.com",
        first_name="Amelia",
        last_name="Hart",
        state="WARMING",
        substate=None,
        city="Austin",
        zip="78701",
        trust_score=0,
        reviews_done=False,
        tier="B",
        blacklisted=False,
        proxy_ip="10.0.0.1:8000",
        batch_id=None,
        adopted_at=None,
        city_changed_at=None,
        last_probe_at=datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc),
        activated_at=None,
        created_at=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
        profile_complete=True,
        use_count=1,
        supplier="acme",
        home_city="Dallas",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_payload_maps_engine_row_to_console_shape():
    account = make_account()
    metro = SimpleNamespace(name="Austin, TX", state="TX", timezone="America/Chicago")
    payload = account_payload(
        account,
        metro,
        score=72,
        components={"warm": 20},
        phase=1,
        day=3,
        gpm_profile_id="gpm-123",
        reviews_posted=2,
    )

    assert payload["id"] == str(account.id)
    assert payload["state_code"] == "TX"
    assert payload["timezone"] == "America/Chicago"
    assert payload["trust_score"] == 72
    assert payload["phase"] == "P1"
    assert payload["phase_day"] == 3
    assert payload["reviews_posted"] == 2
    assert payload["gpm_profile_id"] == "gpm-123"
    assert payload["mode"] == "full_warm"
    assert payload["last_active_at"] == "2026-11-12T08:00:00+00:00"


def test_payload_without_relations_uses_safe_defaults():
    account = make_account(state="NEW", tier=None)
    payload = account_payload(account, None, None, None, None, None, None, None)

    assert payload["state_code"] == ""
    assert payload["timezone"] == "America/New_York"
    assert payload["trust_score"] == 0
    assert payload["phase"] == "P0"
    assert payload["tier"] == "Loai"
    assert payload["gpm_profile_id"] == ""
    assert payload["proxy_city"] == "Austin"


def test_reviews_done_switches_mode():
    account = make_account(reviews_done=True)
    payload = account_payload(account, None, 80, {}, 4, 10, "gpm-9", 12)
    assert payload["mode"] == "post_review"
    assert payload["reviews_done"] == 1


def test_parse_filters_validates_and_normalises():
    batch = uuid.uuid4()
    filters = parse_filters(
        state="active, warming",
        city="  Austin ",
        batch_id=str(batch),
        blacklisted="true",
        sort="-trust_score",
        limit=50,
        offset=10,
    )
    assert filters.states == ("ACTIVE", "WARMING")
    assert filters.city == "Austin"
    assert filters.batch_id == batch
    assert filters.blacklisted is True
    assert filters.sort == "trust_score"
    assert filters.descending is True
    assert filters.limit == 50


@pytest.mark.parametrize(
    "kwargs",
    [
        {"state": "NOT_A_STATE"},
        {"batch_id": "not-a-uuid"},
        {"limit": 0},
        {"limit": 1001},
        {"offset": -1},
        {"sort": "password_hash"},
        {"blacklisted": "maybe"},
    ],
)
def test_parse_filters_rejects_bad_input(kwargs):
    with pytest.raises(ValueError):
        parse_filters(**kwargs)


class _Result:
    def __init__(self, rows=None, total=0):
        self._rows = rows or []
        self._total = total

    def scalar_one(self):
        return self._total

    def scalar_one_or_none(self):
        return self._total if self._total else None

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, rows, total):
        self.rows = rows
        self.total = total
        self.executed = 0

    def execute(self, _stmt):
        self.executed += 1
        return _Result(self.rows, self.total)


def test_list_accounts_wraps_rows_in_pagination_envelope():
    account = make_account()
    metro = SimpleNamespace(name="Austin, TX", state="TX", timezone="America/Chicago")
    row = (account, metro, 64, {}, 0, 1, "gpm-1", 0)
    session = _Session([row], total=1)

    result = list_accounts(session, AccountFilters(limit=25, offset=5))

    assert result["total"] == 1
    assert result["limit"] == 25
    assert result["offset"] == 5
    assert result["items"][0]["email"] == "amelia.hart@example.com"
    assert session.executed == 2  # count + page


def test_get_account_returns_none_when_missing():
    session = _Session([], total=0)
    assert get_account(session, uuid.uuid4()) is None


def test_health_exposes_multi_machine_handshake(monkeypatch):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    import api.admin as admin

    session = _Session([], total="0013")

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(admin, "session_scope", fake_scope)
    client = TestClient(admin.create_app())
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["contract_version"] == admin.CONTRACT_VERSION
    assert body["version"]
    assert body["schema_revision"] == "0013"
    assert body["host"]


def test_fastapi_routes_are_wired(monkeypatch):
    """Exercise the HTTP layer with a fake session (no Postgres needed)."""
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    import api.admin as admin
    from core.config import get_settings

    account = make_account()
    metro = SimpleNamespace(name="Austin, TX", state="TX", timezone="America/Chicago")
    row = (account, metro, 64, {}, 0, 1, "gpm-1", 0)
    session = _Session([row], total=1)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(admin, "session_scope", fake_scope)
    client = TestClient(admin.create_app())
    headers = {"Authorization": f"Bearer {get_settings().admin_token}"}

    unauthorized = client.get("/api/accounts")
    assert unauthorized.status_code == 401

    listed = client.get("/api/accounts?limit=5", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["limit"] == 5
    assert body["items"][0]["email"] == "amelia.hart@example.com"

    bad = client.get("/api/accounts?state=NOPE", headers=headers)
    assert bad.status_code == 400

    detail = client.get(f"/api/accounts/{account.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == str(account.id)

    empty = _Session([], total=0)

    @contextmanager
    def empty_scope():
        yield empty

    monkeypatch.setattr(admin, "session_scope", empty_scope)
    missing = client.get(f"/api/accounts/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404

    invalid_id = client.get("/api/accounts/not-a-uuid", headers=headers)
    assert invalid_id.status_code == 400
