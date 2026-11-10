"""Anti-detect batch 1: no CDP viewport override, block/captcha counters wired.

Three cheap signals that used to be invisible:
- `page.set_viewport_size()` after connect_over_cdp emitted a device-metrics override, so
  screen.innerWidth/outerWidth disagreed with the window GPM opened (classic bot tell).
- blocked pages and captcha challenges only wrote a log line, so block/captcha rate could
  never be measured (no baseline for any anti-detect change).
"""

from __future__ import annotations

import uuid

import pytest
from prometheus_client import REGISTRY

from core.state_machine import StageContext
from db.models import AccountState
from flows.signup import SignupFlow
from flows.warmup import WarmingRunner
from selector_registry.resolver import SelectorRegistry
from tests.fakes import FakeBrowser, FakeGPM, FakePage

pytestmark = pytest.mark.asyncio


def _ctx(browser: FakeBrowser | None = None, html: str = "") -> StageContext:
    ctx = StageContext(account_id=uuid.uuid4(), run_id=uuid.uuid4(), state=AccountState.BROWSER_UP)
    if browser is not None:
        ctx.data["browser"] = browser
    return ctx


def _flow(settings) -> SignupFlow:
    return SignupFlow(settings=settings, gpm=FakeGPM(), registry=None, email_provider=None)


def _sample(name: str, labels: dict) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


# --------------------------------------------------------------------- (a) viewport override


async def test_browser_up_sends_no_viewport_override(settings, monkeypatch):
    """GPM's start_profile(window_size=...) is the only place the window size is set."""
    browser = FakeBrowser()

    async def fake_attach(*args, **kwargs):
        return browser

    monkeypatch.setattr("flows.signup.attach", fake_attach)

    flow = _flow(settings)
    ctx = _ctx()
    ctx.data["profile"] = type("P", (), {"id": "p1"})()
    await flow._enter_browser_up(ctx)

    viewport_events = [ev for ev in browser.page.events if ev[0] == "viewport"]
    assert viewport_events == [], f"viewport override must not be sent after CDP attach: {viewport_events}"


async def test_browser_up_still_delivers_the_page(settings, monkeypatch):
    browser = FakeBrowser()

    async def fake_attach(*args, **kwargs):
        return browser

    monkeypatch.setattr("flows.signup.attach", fake_attach)

    flow = _flow(settings)
    ctx = _ctx()
    ctx.data["profile"] = type("P", (), {"id": "p1"})()
    await flow._enter_browser_up(ctx)

    assert ctx.data["browser"] is browser
    assert ctx.data["browser"].page is browser.page


# --------------------------------------------------------------------- (c) block counter


@pytest.mark.parametrize("stage", ["prewarmed", "form_filled"])
async def test_detect_blocked_increments_counter_by_stage(settings, stage):
    page = FakePage(html="<html><body>Access Denied</body></html>")
    browser = FakeBrowser()
    browser.page = page

    before = _sample("signup_blocked_total", {"stage": stage})
    assert await _flow(settings)._detect_blocked(_ctx(browser), stage=stage) is True
    assert _sample("signup_blocked_total", {"stage": stage}) == before + 1


async def test_clean_page_does_not_touch_block_counter(settings):
    browser = FakeBrowser()
    browser.page = FakePage(html="<html><body>Restaurants near you</body></html>")

    before = _sample("signup_blocked_total", {"stage": "prewarmed"})
    assert await _flow(settings)._detect_blocked(_ctx(browser), stage="prewarmed") is False
    assert _sample("signup_blocked_total", {"stage": "prewarmed"}) == before


# --------------------------------------------------------------------- (c) captcha counter


async def test_captcha_detection_counts_the_kind(settings):
    from adapters.base import CaptchaError

    browser = FakeBrowser()
    browser.page = FakePage(html='<html><div class="g-recaptcha" data-sitekey="k1"></div></html>')

    before = _sample("captcha_detected_total", {"kind": "recaptcha_v2"})
    # No solver chain configured -> CaptchaError, but the detection must already be counted.
    with pytest.raises(CaptchaError):
        await _flow(settings)._enter_captcha(_ctx(browser))
    assert _sample("captcha_detected_total", {"kind": "recaptcha_v2"}) == before + 1


async def test_no_captcha_does_not_count(settings):
    browser = FakeBrowser()
    browser.page = FakePage(html="<html><body>Restaurants near you</body></html>")

    before = _sample("captcha_detected_total", {"kind": "recaptcha_v2"})
    assert await _flow(settings)._enter_captcha(_ctx(browser)) == {"captcha": "none"}
    assert _sample("captcha_detected_total", {"kind": "recaptcha_v2"}) == before


# --------------------------------------------------------------------- (c) warming blocked counter


async def test_warming_rate_limit_increments_blocked_counter(monkeypatch):
    from core.budget import DailyBudget

    runner = WarmingRunner(gpm=None, registry=SelectorRegistry({}), settings=None)

    async def boom(*args, **kwargs):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(runner, "_step", boom)

    browser = FakeBrowser()
    ctx = type("C", (), {"data": {"browser": browser}, "account_id": None})()

    before = _sample("warming_blocked_total", {"reason": "429"})
    await runner.run_session(ctx, budget=DailyBudget.for_phase("P1"), max_seconds=30)
    assert _sample("warming_blocked_total", {"reason": "429"}) == before + 1
