"""Tests for the deterministic per-account fingerprint matrix."""
from __future__ import annotations

from uuid import UUID

import pytest

from core.fingerprint_matrix import WINDOW_SIZES, FingerprintSpec, for_account


def test_deterministic_for_same_account():
    account_id = UUID("12345678-1234-5678-1234-567812345678")
    fp1 = for_account(account_id)
    fp2 = for_account(account_id)
    assert fp1 == fp2
    assert fp1.window_size in WINDOW_SIZES
    assert fp1.os_type == 1
    assert fp1.browser_type in (1, 2)


def test_different_accounts_produce_variation():
    ids = [UUID(f"12345678-1234-5678-1234-5678123456{i:02d}") for i in range(20)]
    specs = [for_account(a) for a in ids]
    sizes = {s.window_size for s in specs}
    types = {s.browser_type for s in specs}
    assert len(sizes) > 1 or len(types) > 1


def test_firefox_only_when_versions_available():
    versions = {"chromium": ["120.0.1"], "firefox": ["130.0.1"]}
    firefox_found = False
    for i in range(50):
        a = UUID(f"12345678-1234-5678-1234-5678123456{i:02d}")
        fp = for_account(a, versions_by_engine=versions)
        if fp.browser_type == 2:
            firefox_found = True
            assert fp.browser_version == "130.0.1"
    assert firefox_found, "expected at least one Firefox bucket in 50 samples"


def test_firefox_fallback_when_empty():
    versions = {"chromium": ["120.0.1"], "firefox": []}
    for i in range(50):
        a = UUID(f"12345678-1234-5678-1234-5678123456{i:02d}")
        fp = for_account(a, versions_by_engine=versions)
        assert fp.browser_type == 1
        assert fp.browser_version == "120.0.1"


def test_version_sort_numeric():
    versions = {"chromium": ["99.0.4844.51", "120.0.6216.2"], "firefox": []}
    fp = for_account(UUID("00000000-0000-0000-0000-000000000001"), versions_by_engine=versions)
    assert fp.browser_version == "120.0.6216.2"


def test_no_versions_leaves_browser_version_empty():
    fp = for_account(UUID("00000000-0000-0000-0000-000000000001"), versions_by_engine={})
    assert fp.browser_version == ""
    assert fp.browser_type == 1


def test_salt_changes_buckets():
    account_id = UUID("12345678-1234-5678-1234-567812345678")
    fp_a = for_account(account_id, salt="salt-a")
    fp_b = for_account(account_id, salt="salt-b")
    assert fp_a != fp_b
