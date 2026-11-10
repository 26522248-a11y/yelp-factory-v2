"""Deterministic per-account fingerprint matrix (anti-detect batch 1).

Keeps os_type=1 (Windows) until verified on real GPM hardware; rotates
window_size and browser_type deterministically from account_id so the farm
does not share one device signature.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Mapping

from obs.log import get_logger

log = get_logger("fingerprint_matrix")

WINDOW_SIZES = [
    "1920,1080",
    "1536,864",
    "1600,900",
    "1366,768",
    "1440,900",
]


@dataclass(frozen=True)
class FingerprintSpec:
    os_type: int
    browser_type: int
    browser_version: str
    window_size: str


def _bucket_index(account_id: uuid.UUID, salt: str, dim: str, buckets: int) -> int:
    """Deterministic but uncorrelated bucket for one dimension."""
    h = hashlib.blake2b(f"{salt}:{account_id}:{dim}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") % buckets


def _max_version(versions: list[str]) -> str:
    """Numeric-aware max; empty list returns empty string."""
    if not versions:
        return ""
    from adapters.gpm_http import _version_sort_key

    return max(versions, key=_version_sort_key)


def for_account(
    account_id: uuid.UUID,
    *,
    salt: str = "yf-fingerprint-v1",
    versions_by_engine: Mapping[str, list[str]] | None = None,
) -> FingerprintSpec:
    """Return deterministic fingerprint values for one account.

    browser_type is bucketed Chrome/Firefox; Firefox is only chosen when the
    GPM install actually exposes firefox versions, otherwise we fall back to
    Chrome to avoid sending a Chrome version with browser_type=2.
    """
    versions_by_engine = versions_by_engine or {}
    window_size = WINDOW_SIZES[_bucket_index(account_id, salt, "window_size", len(WINDOW_SIZES))]

    # 0 = Chrome, 1 = Firefox in this local enum; map to GPM values after.
    browser_kind = _bucket_index(account_id, salt, "browser_kind", 5)
    want_firefox = browser_kind == 1  # ~20% Firefox when available

    firefox_versions = versions_by_engine.get("firefox") or []
    chromium_versions = versions_by_engine.get("chromium") or []

    if want_firefox and firefox_versions:
        browser_type = 2
        browser_version = _max_version(firefox_versions)
    elif chromium_versions:
        browser_type = 1
        browser_version = _max_version(chromium_versions)
    elif firefox_versions:
        # fallback to firefox if chromium list is empty
        browser_type = 2
        browser_version = _max_version(firefox_versions)
    else:
        # no version data at all; let caller resolve later
        browser_type = 1
        browser_version = ""

    return FingerprintSpec(
        os_type=1,  # Windows; do not rotate until verified on real GPM hardware
        browser_type=browser_type,
        browser_version=browser_version,
        window_size=window_size,
    )


def window_size_for_profile(gpm_profile_id: str, default: str = "1280,800") -> str:
    """Read the persisted window_size from the Profile row, if any."""
    try:
        from db.models import Profile
        from db.session import session_scope

        with session_scope() as session:
            row = session.query(Profile).filter_by(gpm_profile_id=gpm_profile_id).one_or_none()
            if row and isinstance(row.fingerprint_json, dict):
                size = row.fingerprint_json.get("window_size")
                if isinstance(size, str) and size:
                    return size
    except Exception as exc:  # noqa: BLE001
        log.debug("window_size_lookup_failed", profile_id=gpm_profile_id, error=str(exc)[:120])
    return default
