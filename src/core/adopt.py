"""``yf adopt``: import bought accounts without touching their profiles (spec B, day 0).

CSV header (required, extra columns ignored):
    email,password,supplier,home_city,metro,proxy[,profile_id,first_name,last_name,zip]

Rules that matter for data integrity:
* the profile is never edited - an existing GPM profile is linked, a missing one is
  created empty and filled only later by the profile phase;
* ``home_city`` is the account's ORIGINAL city and is stored separately from
  ``metro_id``; a blank city is rejected instead of being backfilled to ``''``;
* one inbox = one account, deduplicated inside the file and against the DB;
* ``--dry-run`` performs every check (including the metro lookup) without writing.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from adapters.base import GPMAdapter
from core.clients import list_metros
from core.crypto import SecretBox
from core.importers import PROXY_URL_RE, parse_proxy_line
from db.models import Account, AccountState, Batch, Profile, ProxyPool
from db.session import session_scope
from obs.log import get_logger

log = get_logger("adopt")

REQUIRED_COLUMNS = ("email", "password", "supplier", "home_city", "metro", "proxy")
MIN_PASSWORD_LEN = 8


@dataclass
class AdoptRow:
    line: int
    email: str
    password: str
    supplier: str
    home_city: str
    metro: str
    proxy: str
    profile_id: str | None = None
    first_name: str = ""
    last_name: str = ""
    zip: str = ""


@dataclass
class AdoptReport:
    rows: list[AdoptRow] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    duplicates: int = 0

    @property
    def total(self) -> int:
        return len(self.rows) + len(self.errors) + self.duplicates


def _split_name(email: str) -> tuple[str, str]:
    local = email.split("@")[0]
    parts = [part for part in local.replace(".", " ").replace("_", " ").split() if part]
    first = (parts[0] if parts else "Adopted")[:120].title()
    last = (" ".join(parts[1:]) if len(parts) > 1 else "Account")[:120].title()
    return first, last


def _validate_proxy(raw: str) -> str | None:
    try:
        parse_proxy_line(raw)
    except ValueError as exc:
        return f"invalid_proxy:{exc}"
    return None


def read_adopt_file(path: str | Path, *, existing_emails: set[str] | None = None) -> AdoptReport:
    """Parse + validate the whole file. Never touches GPM or the database."""
    report = AdoptReport()
    existing = {email.lower() for email in (existing_emails or set())}
    seen: set[str] = set()
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
        missing = [name for name in REQUIRED_COLUMNS if name not in header]
        if missing:
            report.errors.append({"line": 1, "error": f"missing_columns:{','.join(missing)}"})
            return report
        for index, raw in enumerate(reader, start=2):
            if not any((value or "").strip() for value in raw.values()):
                continue
            email = (raw.get("email") or "").strip().lower()
            email_key = email
            password = raw.get("password") or ""
            supplier = (raw.get("supplier") or "").strip()
            home_city = (raw.get("home_city") or "").strip()
            metro = (raw.get("metro") or "").strip()
            proxy = (raw.get("proxy") or "").strip()
            if not email or "@" not in email:
                report.errors.append({"line": index, "error": "invalid_email"})
                continue
            if len(password) < MIN_PASSWORD_LEN:
                report.errors.append({"line": index, "error": "password_too_short", "email": email})
                continue
            if not supplier:
                report.errors.append({"line": index, "error": "missing_supplier", "email": email})
                continue
            if not home_city:
                # GAP-12: never let home_city='' through - gate condition 3 would never match.
                report.errors.append({"line": index, "error": "missing_home_city", "email": email})
                continue
            if not metro:
                report.errors.append({"line": index, "error": "missing_metro", "email": email})
                continue
            proxy_error = _validate_proxy(proxy) if proxy else "missing_proxy"
            if proxy_error:
                report.errors.append({"line": index, "error": proxy_error, "email": email})
                continue
            if email_key in seen or email_key in existing:
                report.duplicates += 1
                continue
            seen.add(email_key)
            first_name, last_name = _split_name(email)
            report.rows.append(
                AdoptRow(
                    line=index,
                    email=email,
                    password=password,
                    supplier=supplier,
                    home_city=home_city,
                    metro=metro,
                    proxy=proxy,
                    profile_id=(raw.get("profile_id") or "").strip() or None,
                    first_name=(raw.get("first_name") or "").strip() or first_name,
                    last_name=(raw.get("last_name") or "").strip() or last_name,
                    zip=(raw.get("zip") or "").strip(),
                )
            )
    return report


def _ensure_metro_map() -> dict[str, uuid.UUID]:
    return {item["name"].strip().lower(): uuid.UUID(item["id"]) for item in list_metros()}


def _persist_proxy(session, row: AdoptRow, account_id: uuid.UUID, box: SecretBox) -> ProxyPool:
    parsed = parse_proxy_line(row.proxy)
    proxy = (
        session.query(ProxyPool)
        .filter(ProxyPool.raw == parsed.raw)
        .one_or_none()
    )
    if proxy is None:
        proxy = ProxyPool(
            raw=parsed.raw,
            host=parsed.host,
            port=parsed.port,
            username=parsed.username,
            password_enc=box.encrypt(parsed.password),
            kind="residential",
            status="used",
            accounts_count=0,
            source_file="adopt",
        )
        session.add(proxy)
        session.flush()
    proxy.status = "used"
    proxy.accounts_count = (proxy.accounts_count or 0) + 1
    proxy.reserved_by = account_id
    return proxy


def _link_profile(session, account: Account, row: AdoptRow, gpm: GPMAdapter | None) -> str | None:
    """Link an existing profile, or create an EMPTY one. No profile fields are written."""
    gpm_profile_id = row.profile_id
    if gpm_profile_id is None and gpm is not None:
        from adapters.gpm_ops import ensure_profile, profile_name

        profile, _reused = ensure_profile(
            gpm,
            operation_id=f"adopt:{account.id}",
            name=profile_name(str(account.id)),
            create_kwargs={"raw_proxy": row.proxy},
        )
        gpm_profile_id = profile.id
    if not gpm_profile_id:
        return None

    profile_row = session.query(Profile).filter(Profile.gpm_profile_id == gpm_profile_id).one_or_none()
    if profile_row is None:
        profile_row = Profile(
            gpm_profile_id=gpm_profile_id,
            name=f"yf-adopt-{str(account.id)[:8]}",
            status="active",
            fingerprint_json={"adopted": True, "profile_untouched": True},
        )
        session.add(profile_row)
        session.flush()
    account.profile_id = profile_row.id
    return gpm_profile_id


def adopt_accounts(
    path: str | Path,
    *,
    gpm: GPMAdapter | None = None,
    dry_run: bool = False,
    box: SecretBox | None = None,
    batch: str | None = None,
) -> dict:
    box = box or SecretBox()
    with session_scope() as session:
        existing = {email for (email,) in session.query(Account.email).all()}
        metros = _ensure_metro_map()
        batch_row = session.query(Batch).filter(Batch.name == batch).one_or_none() if batch else None

    report = read_adopt_file(path, existing_emails=existing)
    unknown = [row for row in report.rows if row.metro.lower() not in metros]
    if unknown:
        # A dry run must fail the same rows a real run would, not report them as valid.
        report.errors.extend({"line": row.line, "error": f"unknown_metro:{row.metro}", "email": row.email} for row in unknown)
        report.rows = [row for row in report.rows if row.metro.lower() in metros]
    payload: dict = {
        "total": report.total,
        "valid": len(report.rows),
        "invalid": len(report.errors),
        "duplicates": report.duplicates,
    }
    if report.errors:
        payload["errors"] = report.errors[:50]
    if batch and batch_row is None:
        payload["batch_error"] = f"batch '{batch}' not found"
    if dry_run:
        payload["dry_run"] = True
        payload["accounts"] = [
            {
                "line": row.line,
                "email": row.email,
                "supplier": row.supplier,
                "home_city": row.home_city,
                "metro": row.metro,
                "proxy": f"{row.proxy.split(':')[0]}:{row.proxy.split(':')[1]}",
                "profile_id": row.profile_id,
                "metro_known": True,
            }
            for row in report.rows
        ]
        return payload
    if batch and batch_row is None:
        return payload

    adopted: list[dict] = []
    now = datetime.now(timezone.utc)
    for row in report.rows:
        metro_id = metros.get(row.metro.lower())
        if metro_id is None:
            payload["errors"] = [*(payload.get("errors") or []), {"line": row.line, "error": f"unknown_metro:{row.metro}"}]
            continue
        account_id = uuid.uuid4()
        try:
            with session_scope() as session:
                account = Account(
                    id=account_id,
                    batch_id=batch_row.id if batch_row else None,
                    email=row.email,
                    email_alias=row.email,
                    email_password_enc=box.encrypt(row.password),
                    password_enc=box.encrypt(row.password),
                    first_name=row.first_name,
                    last_name=row.last_name,
                    zip=row.zip or "00000",
                    city=row.home_city,
                    home_city=row.home_city,
                    supplier=row.supplier,
                    metro_id=metro_id,
                    state=AccountState.ACTIVE.value,
                    reviews_done=True,  # arrived pre-warmed: maintenance ladder, no profile edits
                    adopted_at=now,
                    use_count=0,
                    friend_count=0,
                    tip_count=0,
                    checkin_count=0,
                    blacklisted=False,
                )
                session.add(account)
                session.flush()
                proxy = _persist_proxy(session, row, account_id, box)
                account.proxy_pool_id = proxy.id
                account.proxy_ip = proxy.host
                gpm_profile_id = _link_profile(session, account, row, gpm)
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
            log.warning("adopt_row_failed", email=row.email, error=str(exc)[:200])
            payload["errors"] = [*(payload.get("errors") or []), {"line": row.line, "error": str(exc)[:200]}]
            continue
        adopted.append(
            {
                "account": str(account_id),
                "email": row.email,
                "supplier": row.supplier,
                "home_city": row.home_city,
                "metro": row.metro,
                "profile_id": gpm_profile_id,
                "profile_created": gpm_profile_id is not None and row.profile_id is None,
            }
        )
    payload["adopted"] = len(adopted)
    payload["accounts"] = adopted
    log.info("accounts_adopted", count=len(adopted), path=str(path))
    return payload
