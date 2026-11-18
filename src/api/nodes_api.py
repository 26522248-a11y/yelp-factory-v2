"""Node registry for multi-machine deployments.

Every console/worker posts a heartbeat; the console lists every machine and its
last-seen age. Pure payload functions keep this unit-testable without Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db.models import BrowserSlot, Node, Run

ONLINE_WINDOW = timedelta(seconds=120)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def node_payload(
    node: Node,
    now: datetime | None = None,
    *,
    progress: dict[str, int] | None = None,
    slots: int = 0,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    last_seen = _utc(node.last_seen)
    age = int((now - last_seen).total_seconds()) if last_seen else None
    online = age is not None and age <= int(ONLINE_WINDOW.total_seconds())
    status = "online" if online else ("offline" if node.status == "online" else node.status)
    return {
        "id": node.id,
        "name": node.name,
        "hostname": node.hostname,
        "role": node.role,
        "version": node.version,
        "capacity": int(node.capacity or 0),
        "status": status,
        "online": online,
        "age_seconds": age,
        "meta": node.meta or {},
        "progress": progress
        or {"running": 0, "pending": 0, "done": 0, "failed": 0},
        "slots": int(slots),
        "first_seen": _utc(node.first_seen).isoformat() if node.first_seen else None,
        "last_seen": last_seen.isoformat() if last_seen else None,
    }


def _progress_by_node(session: Session, now: datetime) -> dict[str, dict[str, int]]:
    """Runs in the last 24h (plus anything still pending/running), grouped by node."""
    cutoff = now - timedelta(hours=24)
    rows = session.execute(
        select(Run.node_id, Run.state, func.count())
        .where(Run.node_id.is_not(None))
        .where(or_(Run.started_at >= cutoff, Run.state.in_(("PENDING", "RUNNING"))))
        .group_by(Run.node_id, Run.state)
    ).all()
    bucket = {
        "RUNNING": "running",
        "PENDING": "pending",
        "DONE": "done",
        "FAILED": "failed",
        "ABORTED": "failed",
    }
    result: dict[str, dict[str, int]] = {}
    for node_key, state, count in rows:
        target = result.setdefault(
            node_key, {"running": 0, "pending": 0, "done": 0, "failed": 0}
        )
        target[bucket.get(state, "done")] += int(count)
    return result


def _slots_by_node(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(BrowserSlot.node_id, func.count())
        .where(BrowserSlot.node_id.is_not(None))
        .group_by(BrowserSlot.node_id)
    ).all()
    return {node_key: int(count) for node_key, count in rows}


def list_nodes(session: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows = session.scalars(select(Node).order_by(Node.last_seen.desc())).all()
    try:
        progress = _progress_by_node(session, now)
        slots = _slots_by_node(session)
    except Exception:  # noqa: BLE001 - telemetry must not break the listing
        progress, slots = {}, {}
    items = [
        node_payload(row, now, progress=progress.get(row.id), slots=slots.get(row.id, 0))
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "online": sum(1 for item in items if item["online"]),
        "online_window_seconds": int(ONLINE_WINDOW.total_seconds()),
    }


def upsert_node(
    session: Session, data: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    node = session.get(Node, data["node_id"])
    if node is None:
        node = Node(id=data["node_id"], first_seen=now)
        session.add(node)
    node.name = data["name"]
    node.hostname = data.get("hostname") or ""
    node.role = data.get("role") or "console"
    node.version = data.get("version")
    node.capacity = int(data.get("capacity") or 0)
    node.meta = data.get("meta") or {}
    node.status = "online"
    node.last_seen = now
    session.flush()
    return node_payload(node, now)
