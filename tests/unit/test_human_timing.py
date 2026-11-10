"""YF_HUMAN_TIME_SCALE knob: production cadence vs test speed."""

from __future__ import annotations

import asyncio
import time

import pytest


async def _measure(coro) -> float:
    start = time.monotonic()
    await coro
    return time.monotonic() - start


@pytest.mark.asyncio
async def test_sleep_s_zero_scale_is_instant(monkeypatch):
    from human.timing import sleep_s

    monkeypatch.setenv("YF_HUMAN_TIME_SCALE", "0.0")
    elapsed = await _measure(sleep_s(0.5))
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_sleep_s_default_scale_sleeps(monkeypatch):
    from human.timing import sleep_s

    monkeypatch.setenv("YF_HUMAN_TIME_SCALE", "1.0")
    elapsed = await _measure(sleep_s(0.15))
    assert elapsed >= 0.1


@pytest.mark.asyncio
async def test_sleep_s_half_scale(monkeypatch):
    from human.timing import sleep_s

    monkeypatch.setenv("YF_HUMAN_TIME_SCALE", "0.5")
    elapsed = await _measure(sleep_s(0.2))
    assert 0.05 <= elapsed < 0.2


@pytest.mark.asyncio
async def test_idle_zero_scale(monkeypatch):
    from human.timing import idle

    monkeypatch.setenv("YF_HUMAN_TIME_SCALE", "0.0")

    class FakePage:
        def __init__(self):
            self.waited = 0

        async def wait_for_timeout(self, ms: int) -> None:
            self.waited = ms
            await asyncio.sleep(0)

    page = FakePage()
    await idle(page, low=1.0, high=2.0)
    assert page.waited == 0


@pytest.mark.asyncio
async def test_idle_default_scale(monkeypatch):
    from human.timing import idle

    monkeypatch.setenv("YF_HUMAN_TIME_SCALE", "1.0")

    class FakePage:
        def __init__(self):
            self.waited = 0

        async def wait_for_timeout(self, ms: int) -> None:
            self.waited = ms
            await asyncio.sleep(0)

    page = FakePage()
    await idle(page, low=1.0, high=2.0)
    assert 900 <= page.waited <= 2100


def test_invalid_scale_falls_back_to_one(monkeypatch):
    from core.config import load_settings, reset_settings

    monkeypatch.setenv("YF_HUMAN_TIME_SCALE", "not-a-number")
    reset_settings()
    settings = load_settings()
    assert settings.human_time_scale == 1.0
