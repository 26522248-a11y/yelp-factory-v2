"""geolocation_mode=1 at profile create + no runtime grant_permissions (anti-detect batch).

GPM global-v1 create API has no lat/lon field, so coordinates still have to be
pushed per session with ``set_geolocation``. What we removed is the redundant
``grant_permissions`` CDP call: the permission is granted once, at profile
create time (``geolocation_mode=1`` = Allow).
"""

from __future__ import annotations

import json

import httpx
import pytest

from adapters.gpm_http import GPMHttpClient
from flows.post_review_warm import PostReviewWarmRunner
from selector_registry.resolver import SelectorRegistry, SelectorRule
from tests.fakes import FakePage

pytestmark = pytest.mark.asyncio


REGISTRY = SelectorRegistry(
    {"warmup.checkin": [SelectorRule("css", "button:has-text('Check-in')", 1)]}
)


def _client(handler) -> GPMHttpClient:
    return GPMHttpClient(base_url="http://127.0.0.1:9495", transport=httpx.MockTransport(handler))


def _create_capture() -> dict:
    captured: dict = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"id": "p1", "name": captured["name"], "browser": {"version": "153.0.8010.53"}},
                "message": "OK",
                "sender": "GPMLoginGlobal",
            },
        )

    return captured, handler


async def test_create_profile_defaults_geolocation_mode_allow():
    """Default = 1 (Allow) so the browser never shows a permission prompt."""
    captured, handler = _create_capture()
    _client(handler).create_profile(name="yf-geo", raw_proxy="1.1.1.1:8000:u:p", browser_version="153.0.8010.53")
    assert captured["geolocation_mode"] == 1


async def test_geolocation_mode_still_overridable_through_fingerprint_kwargs():
    """The fingerprint kwargs still win - callers can force Block (3) if a proxy needs it."""
    captured, handler = _create_capture()
    _client(handler).create_profile(
        name="yf-geo-block",
        raw_proxy="1.1.1.1:8000:u:p",
        browser_version="153.0.8010.53",
        geolocation_mode=3,
    )
    assert captured["geolocation_mode"] == 3


class _RecordingContext:
    """Records CDP-ish calls so we can assert grant_permissions is gone."""

    def __init__(self) -> None:
        self.grants: list[tuple] = []
        self.geolocations: list[dict] = []

    async def grant_permissions(self, permissions, **kwargs) -> None:
        self.grants.append((tuple(permissions), kwargs))

    async def set_geolocation(self, coords: dict) -> None:
        self.geolocations.append(dict(coords))


class _Log:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def __call__(self, kind: str, *args, **kwargs) -> None:
        self.events.append((kind, args))

    def warning(self, kind: str, **kwargs) -> None:
        self.events.append(("warning", kind))


async def test_checkin_pushes_coordinates_without_grant_permissions(settings):
    settings.post_review.rest_between_actions_s = (0, 0)
    runner = PostReviewWarmRunner(registry=REGISTRY, settings=settings)

    page = FakePage(url="https://www.yelp.com/biz/some-cafe")
    page.add("button:has-text('Check-in')", visible=True)
    context = _RecordingContext()
    page.context = context  # the real page exposes .context; FakePage keeps _context

    log = _Log()
    outcome = await runner._checkin(page, log, city="brooklyn")

    assert outcome == "checkin"
    assert context.grants == [], "grant_permissions must not be called at runtime any more"
    assert len(context.geolocations) == 1
    base_lat, base_lon = runner._geo_for("brooklyn")
    coords = context.geolocations[0]
    assert abs(coords["latitude"] - base_lat) <= 0.0031
    assert abs(coords["longitude"] - base_lon) <= 0.0031
    assert not [e for e in log.events if e[0] == "warning"], "no geolocation warning expected"


async def test_checkin_survives_context_without_set_geolocation(settings):
    """Context objects without set_geolocation (older fakes) must not break the check-in."""
    settings.post_review.rest_between_actions_s = (0, 0)
    runner = PostReviewWarmRunner(registry=REGISTRY, settings=settings)

    page = FakePage(url="https://www.yelp.com/biz/some-cafe")
    page.add("button:has-text('Check-in')", visible=True)
    page.context = object()

    outcome = await runner._checkin(page, _Log(), city=None)
    assert outcome == "checkin"
