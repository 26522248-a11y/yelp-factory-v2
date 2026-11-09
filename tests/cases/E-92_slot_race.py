"""E-92: browser slot concurrency - 5 threads race, exactly 2 may win (B2).

Runs against the real Postgres; skipped when it is unreachable.
"""

from __future__ import annotations

import threading

import pytest

from core.lock import acquire_slot, active_slots, release_slot
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready")


def _clear_slots():
    with session_scope() as session:
        from sqlalchemy import text

        session.execute(text("DELETE FROM browser_slots"))


def test_slot_acquire_is_atomic_under_race():
    _clear_slots()
    winners: list = []
    lock = threading.Lock()

    def worker(i: int):
        token = acquire_slot(f"race-{i}", 2, purpose="test")
        if token is not None:
            with lock:
                winners.append(token)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    try:
        assert len(winners) == 2, f"expected exactly 2 winners, got {len(winners)}"
        assert active_slots() == 2
    finally:
        for token in winners:
            release_slot(token)
        _clear_slots()


def test_release_frees_a_slot_for_the_next_worker():
    _clear_slots()
    first = acquire_slot("r1", 2, purpose="test")
    second = acquire_slot("r2", 2, purpose="test")
    try:
        assert first and second
        assert acquire_slot("r3", 2, purpose="test") is None
        release_slot(first)
        third = acquire_slot("r4", 2, purpose="test")
        assert third is not None
        release_slot(third)
    finally:
        release_slot(first)
        release_slot(second)
        _clear_slots()
