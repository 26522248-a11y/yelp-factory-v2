# -*- coding: utf-8 -*-
"""Unit tests for GPM browser version resolution and engine-aware parsing."""
from __future__ import annotations

from adapters.base import ProfileDTO
from adapters.gpm_http import GPMHttpClient, _version_sort_key


class _FakeGPMClient(GPMHttpClient):
    def __init__(self, browsers_payload: list | None = None, profiles: list[ProfileDTO] | None = None):
        super().__init__(base_url="http://127.0.0.1:9495")
        self._browsers = browsers_payload or []
        self._profiles = profiles or []
        self.create_calls: list[dict] = []
        self._next_id = 0

    def _call(self, method: str, path: str, **kwargs):
        if path == "/api/v1/browsers":
            return self._browsers
        if path == "/api/v1/profiles/create" and method == "POST":
            body = kwargs.get("json", {})
            self.create_calls.append(body)
            self._next_id += 1
            return {
                "id": f"p{self._next_id}",
                "name": body.get("name"),
                "group_id": None,
                "storage_path": f"p{self._next_id}",
                "raw_proxy": body.get("raw_proxy", ""),
                "browser": {
                    "name": "chrome" if body.get("browser_type", 1) == 1 else "firefox",
                    "version": body.get("browser_version", ""),
                },
                "os": "windows",
                "created_at": "2026-11-04 10:00:00",
                "updated_at": "2026-11-04 10:00:00",
                "tags": [],
            }
        raise RuntimeError(f"unexpected {method} {path}")

    def list_profiles(self):
        return self._profiles


def test_version_sort_key_numeric():
    versions = ["99.0.4844.51", "120.0.6216.2", "119.0.0", "120.0.6216.10"]
    # 120.0.6216.10 sorts before 120.0.6216.2 numerically (10 < 2 is false).
    assert sorted(versions, key=_version_sort_key) == [
        "99.0.4844.51",
        "119.0.0",
        "120.0.6216.10",
        "120.0.6216.2",
    ]


def test_resolve_browser_version_prefers_largest_numeric():
    payload = [
        {"version": "99.0.4844.51"},
        {"version": "120.0.6216.2"},
        {"version": "119.0.0"},
    ]
    client = _FakeGPMClient(payload)
    assert client.resolve_browser_version() == "120.0.6216.2"


def test_resolve_browser_version_engine_aware():
    payload = [
        {"version": "120.0.6216.2", "engine": "chromium"},
        {"version": "99.0.0", "engine": "chromium"},
        {"version": "132.0.0", "engine": "firefox"},
    ]
    client = _FakeGPMClient(payload)
    assert client.resolve_browser_version(engine="chromium") == "120.0.6216.2"
    assert client.resolve_browser_version(engine="firefox") == "132.0.0"


def test_resolve_browser_version_payload_without_engine_defaults_to_chromium():
    payload = [
        {"version": "153.0.8010.53"},
        {"version": "120.0.6216.2"},
    ]
    client = _FakeGPMClient(payload)
    assert client.resolve_browser_version() == "153.0.8010.53"
    assert client.resolve_browser_version(engine="firefox") == "153.0.8010.53"


def test_resolve_browser_version_browser_type_int_field():
    payload = [
        {"version": "120.0.0", "browser_type": 1},
        {"version": "132.0.0", "browser_type": 2},
    ]
    client = _FakeGPMClient(payload)
    assert client.resolve_browser_version(engine="chromium") == "120.0.0"
    assert client.resolve_browser_version(engine="firefox") == "132.0.0"


def test_create_profile_uses_firefox_version_when_browser_type_is_two():
    payload = [
        {"version": "120.0.0", "engine": "chromium"},
        {"version": "132.0.0", "engine": "firefox"},
    ]
    client = _FakeGPMClient(payload)
    profile = client.create_profile(name="yf-test-ff", browser_type=2, raw_proxy="1.1.1.1:8000:u:p")
    assert profile.browser_version == "132.0.0"
    assert client.create_calls[-1]["browser_version"] == "132.0.0"


def test_create_profile_uses_chromium_version_by_default():
    payload = [
        {"version": "120.0.0", "engine": "chromium"},
        {"version": "132.0.0", "engine": "firefox"},
    ]
    client = _FakeGPMClient(payload)
    profile = client.create_profile(name="yf-test-chrome", raw_proxy="1.1.1.1:8000:u:p")
    assert profile.browser_version == "120.0.0"
    assert client.create_calls[-1]["browser_version"] == "120.0.0"
