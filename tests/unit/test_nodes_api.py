"""Unit tests for the multi-machine node registry (no database required)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from api.nodes_api import ONLINE_WINDOW, list_nodes, node_payload, upsert_node
from db.models import Node


def make_node(**overrides) -> Node:
    now = datetime.now(timezone.utc)
    values = dict(
        id="node-1",
        name="operator-a",
        hostname="PC-A",
        role="console",
        version="0.1.0",
        capacity=0,
        status="online",
        meta={"platform": "win32"},
        first_seen=now - timedelta(hours=2),
        last_seen=now,
    )
    values.update(overrides)
    return Node(**values)


def test_online_node_payload():
    now = datetime.now(timezone.utc)
    payload = node_payload(
        make_node(last_seen=now - timedelta(seconds=30)),
        now,
        progress={"running": 2, "pending": 1, "done": 7, "failed": 0},
        slots=2,
    )
    assert payload["online"] is True
    assert payload["status"] == "online"
    assert payload["age_seconds"] == 30
    assert payload["hostname"] == "PC-A"
    assert payload["progress"]["running"] == 2
    assert payload["slots"] == 2


def test_stale_node_payload_marks_offline():
    now = datetime.now(timezone.utc)
    stale = now - ONLINE_WINDOW - timedelta(seconds=1)
    payload = node_payload(make_node(last_seen=stale), now)
    assert payload["online"] is False
    assert payload["status"] == "offline"


def test_naive_timestamps_are_treated_as_utc():
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(seconds=5)).replace(tzinfo=None)
    payload = node_payload(make_node(last_seen=naive), now)
    assert payload["online"] is True


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _NodeSession:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.added = []
        self.flushed = False

    def scalars(self, _stmt):
        return _Scalars(self.rows)

    def get(self, _model, key):
        return next((row for row in self.rows if row.id == key), None)

    def add(self, obj):
        self.rows.append(obj)
        self.added.append(obj)

    def flush(self):
        self.flushed = True


def test_list_nodes_reports_online_count():
    now = datetime.now(timezone.utc)
    session = _NodeSession(
        [
            make_node(id="a", last_seen=now),
            make_node(id="b", last_seen=now - ONLINE_WINDOW - timedelta(minutes=1)),
        ]
    )
    result = list_nodes(session, now)
    assert result["total"] == 2
    assert result["online"] == 1
    assert result["online_window_seconds"] == 120


def test_upsert_creates_then_updates():
    now = datetime.now(timezone.utc)
    session = _NodeSession()
    created = upsert_node(
        session,
        {
            "node_id": "worker-1",
            "name": "worker-a",
            "hostname": "PC-W",
            "role": "worker",
            "version": "0.1.0",
            "capacity": 8,
            "meta": {"gpm": "3.4.1"},
        },
        now,
    )
    assert created["role"] == "worker"
    assert created["capacity"] == 8
    assert session.flushed is True

    updated = upsert_node(
        session,
        {
            "node_id": "worker-1",
            "name": "worker-a-renamed",
            "hostname": "PC-W",
            "role": "worker",
            "version": "0.1.1",
            "capacity": 4,
            "meta": {},
        },
        now + timedelta(seconds=10),
    )
    assert updated["name"] == "worker-a-renamed"
    assert updated["capacity"] == 4
    assert len(session.added) == 1


def test_routes_are_wired(monkeypatch):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    import api.admin as admin
    from core.config import get_settings

    now = datetime.now(timezone.utc)
    session = _NodeSession([make_node(last_seen=now)])

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(admin, "session_scope", fake_scope)
    client = TestClient(admin.create_app())
    headers = {"Authorization": f"Bearer {get_settings().admin_token}"}

    assert client.get("/api/nodes").status_code == 401

    listed = client.get("/api/nodes", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    beat = client.post(
        "/api/nodes/heartbeat",
        headers=headers,
        json={
            "node_id": "console-9",
            "name": "operator-b",
            "hostname": "PC-B",
            "role": "console",
            "version": "0.1.0",
            "capacity": 0,
            "meta": {},
        },
    )
    assert beat.status_code == 200
    assert beat.json()["id"] == "console-9"

    bad = client.post(
        "/api/nodes/heartbeat",
        headers=headers,
        json={"node_id": "x", "name": "x", "role": "root"},
    )
    assert bad.status_code == 422
