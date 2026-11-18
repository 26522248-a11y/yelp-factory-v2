"""Stable identity + heartbeat for an engine/worker process.

Consoles heartbeat through the admin API; long-running engine processes write the
same `nodes` row directly so the Nodes screen sees them even when the API process
is separate (``yf serve`` + ``yf schedule`` on one machine).
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import socket
import threading
from datetime import datetime, timezone

from db.models import Node
from db.session import session_scope
from obs.log import get_logger

log = get_logger("nodes")


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", value)[:120]


def node_id() -> str:
    """Stable machine id: YF_NODE_ID or the hostname."""
    return _sanitize(os.getenv("YF_NODE_ID") or socket.gethostname() or "engine")


NODE_ID = node_id()
DISPLAY_NAME = os.getenv("YF_NODE_NAME") or socket.gethostname() or NODE_ID


def _version() -> str:
    try:
        return importlib.metadata.version("yelp-factory")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def heartbeat(
    *,
    role: str = "worker",
    capacity: int = 0,
    meta: dict | None = None,
) -> bool:
    """Upsert this machine's row. Never raises: nodes are observability only."""
    try:
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            node = session.get(Node, NODE_ID)
            if node is None:
                node = Node(id=NODE_ID, first_seen=now)
                session.add(node)
            node.name = DISPLAY_NAME
            node.hostname = socket.gethostname() or NODE_ID
            node.role = role
            node.version = _version()
            node.capacity = int(capacity or 0)
            node.meta = meta or {}
            node.status = "online"
            node.last_seen = now
        return True
    except Exception as exc:  # noqa: BLE001 - never let telemetry break work
        log.warning("node_heartbeat_failed", error=str(exc)[:180])
        return False


def start_heartbeat_loop(
    *, role: str, capacity: int = 0, interval_s: int = 30, meta: dict | None = None
) -> None:
    """Send one heartbeat now and then every ``interval_s`` on a daemon thread."""
    heartbeat(role=role, capacity=capacity, meta=meta)

    def _loop() -> None:
        stop = threading.Event()
        while not stop.wait(interval_s):
            heartbeat(role=role, capacity=capacity, meta=meta)

    threading.Thread(target=_loop, name="node-heartbeat", daemon=True).start()
