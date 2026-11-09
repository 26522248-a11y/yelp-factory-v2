"""E-91: clients import validates taxonomy, metro, facts and (optionally) the biz id."""

from __future__ import annotations

import csv
import uuid
from pathlib import Path

import pytest

from core.clients import ALLOWED_CATEGORIES, ensure_metro, import_clients
from db.models import Client
from db.session import session_scope

pytestmark = pytest.mark.usefixtures("db_ready")

HEADER = ["business_name", "yelp_biz_id", "category", "metro", "address", "facts"]


def _write_csv(tmp_path: Path, rows: list[list[str]]) -> Path:
    path = tmp_path / "clients.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def test_import_rejects_bad_rows_and_keeps_good_ones(tmp_path):
    metro_name = "Validation Metro, NY"
    ensure_metro(metro_name)
    biz = f"valid-{uuid.uuid4().hex[:8]}"
    rows = [
        ["Good Diner", biz, "restaurants", metro_name, "", '{"menu": ["eggs"], "price_examples": ["$9"]}'],
        ["Bad Category", f"bad-{uuid.uuid4().hex[:6]}", "spaceships", metro_name, "", '{"menu": ["x"], "price_examples": ["$1"]}'],
        ["No Facts", f"nofacts-{uuid.uuid4().hex[:6]}", "restaurants", metro_name, "", ""],
        ["Thin Facts", f"thin-{uuid.uuid4().hex[:6]}", "restaurants", metro_name, "", '{"menu": ["x"]}'],
        ["Unknown Metro", f"unk-{uuid.uuid4().hex[:6]}", "restaurants", "Nowhere, ZZ", "", '{"menu": ["x"], "price_examples": ["$1"]}'],
        ["Bad Facts Types", f"bft-{uuid.uuid4().hex[:6]}", "restaurants", metro_name, "", '{"menu": [123], "price_examples": ["$1"]}'],
    ]
    path = _write_csv(tmp_path, rows)

    dry = import_clients(path, dry_run=True)
    assert dry["valid"] == 1
    assert dry["invalid"] == 5
    reasons = " ".join(error["error"] for error in dry["errors"])
    assert "taxonomy" in reasons
    assert "facts" in reasons
    assert "metro" in reasons

    real = import_clients(path)
    assert real["created"] == 1
    with session_scope() as session:
        saved = session.query(Client).filter(Client.yelp_biz_id == biz).one_or_none()
        assert saved is not None
        session.delete(saved)


def test_taxonomy_covers_the_five_bands():
    assert ALLOWED_CATEGORIES == {"restaurants", "home_services", "auto", "beauty", "health"}
