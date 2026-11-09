"""Global system flags (governor switches) stored in the database."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.models import SystemFlag
from db.session import session_scope
from obs.log import get_logger

log = get_logger("flags")


def get_flag(key: str, default: dict | None = None) -> dict:
    with session_scope() as session:
        row = session.get(SystemFlag, key)
        return dict(row.value or {}) if row is not None else dict(default or {})


def set_flag(key: str, value: dict[str, Any]) -> None:
    with session_scope() as session:
        row = session.get(SystemFlag, key)
        if row is None:
            session.add(SystemFlag(key=key, value=value, updated_at=datetime.now(timezone.utc)))
        else:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
    log.info("flag_set", key=key, value=value)
