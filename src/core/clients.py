"""Client import and metro management for the review pool (2026-11-09).

CSV columns (header required):
    business_name,yelp_biz_id,category,metro,address,facts
``facts`` is optional JSON: {"menu": [...], "staff": [...], "price_examples": [...], "notes": "..."}
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path

from db.models import Client, Metro
from db.session import session_scope
from obs.log import get_logger

log = get_logger("clients")

MAX_ACCOUNTS_PER_METRO = 8  # 4-8 accounts per metro is the ceiling before opening a new metro

# Category taxonomy used by the keyword mix and the no-two-same-category-per-week rule.
ALLOWED_CATEGORIES = {"restaurants", "home_services", "auto", "beauty", "health"}


def _validate_facts(facts: dict) -> str | None:
    if not isinstance(facts, dict):
        return "facts must be an object"
    menu = facts.get("menu")
    price = facts.get("price_examples")
    if not isinstance(menu, list) or not menu:
        return "facts.menu must be a non-empty list (dish/service names for concrete details)"
    if not isinstance(price, list) or not price:
        return "facts.price_examples must be a non-empty list (specific prices)"
    if not all(isinstance(item, str) and item.strip() for item in menu):
        return "facts.menu must contain non-empty strings"
    if not all(isinstance(item, str) and item.strip() for item in price):
        return "facts.price_examples must contain non-empty strings"
    staff = facts.get("staff")
    if staff is not None and (not isinstance(staff, list) or not all(isinstance(s, str) and s.strip() for s in staff)):
        return "facts.staff must be a list of non-empty strings when present"
    notes = facts.get("notes")
    if notes is not None and not isinstance(notes, str):
        return "facts.notes must be a string when present"
    return None


def _probe_biz(yelp_biz_id: str) -> bool | None:
    """200/301/302 => exists, 404 => invalid, None => could not check."""
    try:
        import httpx

        response = httpx.get(
            f"https://www.yelp.com/biz/{yelp_biz_id}",
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if response.status_code == 404:
            return False
        if response.status_code < 400:
            return True
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("biz_probe_failed", biz=yelp_biz_id, error=str(exc)[:120])
        return None


def ensure_metro(name: str, timezone: str | None = None) -> uuid.UUID:
    name = name.strip()
    with session_scope() as session:
        row = session.query(Metro).filter(Metro.name == name).one_or_none()
        if row is None:
            state = name.split(",")[-1].strip()[:8] if "," in name else ""
            row = Metro(name=name, state=state, timezone=timezone or "America/New_York")
            session.add(row)
            session.flush()
        elif timezone and row.timezone != timezone:
            row.timezone = timezone
        return row.id


def list_metros() -> list[dict]:
    with session_scope() as session:
        rows = session.query(Metro).order_by(Metro.name).all()
        return [{"id": str(r.id), "name": r.name, "state": r.state} for r in rows]


def import_clients(
    path: str | Path,
    *,
    dry_run: bool = False,
    probe: bool = False,
    create_metros: bool = False,
) -> dict:
    path = Path(path)
    valid: list[dict] = []
    errors: list[dict] = []
    known_metros: set[str] = {m["name"] for m in list_metros()}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader, start=2):
            name = (row.get("business_name") or "").strip()
            biz_id = (row.get("yelp_biz_id") or "").strip()
            metro = (row.get("metro") or "").strip()
            category = (row.get("category") or "other").strip().lower()
            if not name or not biz_id or not metro:
                errors.append({"line": index, "error": "missing business_name/yelp_biz_id/metro"})
                continue
            if category not in ALLOWED_CATEGORIES:
                errors.append(
                    {"line": index, "error": f"category '{category}' not in taxonomy {sorted(ALLOWED_CATEGORIES)}"}
                )
                continue
            if metro not in known_metros:
                if not create_metros:
                    errors.append({"line": index, "error": f"metro '{metro}' not in metros (use --create-metros to add)"})
                    continue
            facts: dict = {}
            raw_facts = (row.get("facts") or "").strip()
            if not raw_facts:
                errors.append({"line": index, "error": "facts JSON is required (menu + price_examples)"})
                continue
            try:
                facts = json.loads(raw_facts)
            except json.JSONDecodeError as exc:
                errors.append({"line": index, "error": f"facts not JSON: {exc}"})
                continue
            facts_error = _validate_facts(facts)
            if facts_error:
                errors.append({"line": index, "error": facts_error})
                continue
            if probe:
                exists = _probe_biz(biz_id)
                if exists is False:
                    errors.append({"line": index, "error": f"yelp_biz_id '{biz_id}' returned 404"})
                    continue
                if exists is None:
                    log.warning("biz_probe_inconclusive", line=index, biz=biz_id)
            valid.append(
                {"business_name": name, "yelp_biz_id": biz_id, "metro": metro, "category": category,
                 "address": (row.get("address") or "").strip() or None, "facts": facts}
            )

    if dry_run:
        return {"valid": len(valid), "invalid": len(errors), "errors": errors, "dry_run": True}

    created = 0
    updated = 0
    with session_scope() as session:
        for item in valid:
            metro_id = ensure_metro(item["metro"])
            existing = session.query(Client).filter(Client.yelp_biz_id == item["yelp_biz_id"]).one_or_none()
            if existing is None:
                session.add(
                    Client(
                        business_name=item["business_name"],
                        metro_id=metro_id,
                        category=item["category"],
                        yelp_biz_id=item["yelp_biz_id"],
                        address=item["address"],
                        facts=item["facts"],
                    )
                )
                created += 1
            else:
                existing.business_name = item["business_name"]
                existing.metro_id = metro_id
                existing.category = item["category"]
                existing.address = item["address"] or existing.address
                if item["facts"]:
                    existing.facts = item["facts"]
                updated += 1
    log.info("clients_imported", created=created, updated=updated, invalid=len(errors))
    return {"valid": len(valid), "invalid": len(errors), "created": created, "updated": updated, "errors": errors}


def list_clients(metro: str | None = None, limit: int = 100) -> list[dict]:
    with session_scope() as session:
        query = session.query(Client).order_by(Client.business_name).limit(limit)
        if metro:
            metro_row = session.query(Metro).filter(Metro.name == metro).one_or_none()
            if metro_row is None:
                return []
            query = query.filter(Client.metro_id == metro_row.id)
        rows = query.all()
        return [
            {"id": str(r.id), "business_name": r.business_name, "yelp_biz_id": r.yelp_biz_id,
             "category": r.category, "facts": bool(r.facts)}
            for r in rows
        ]
