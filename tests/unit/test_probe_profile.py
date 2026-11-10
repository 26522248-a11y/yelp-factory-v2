"""`yf probe-profile` signals: read-only anti-detect evidence, bounded and failure-proof.

The QA box has no GPM, so the only way to prove this code path is a fake page whose
`evaluate()` returns fixed values (and, in one test, hangs) — the assertions are about the
contract: which signals are collected, that a failing/slow eval degrades to a string instead
of aborting, and that the GPM profile is always released.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from cli import collect_page_signals, main
from tests.fakes import FakeBrowser, FakeGPM, FakePage

FINGERPRINT = {
    "webdriver": False,
    "platform": "Win32",
    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "languages": ["en-US", "en"],
    "hardwareConcurrency": 8,
    "deviceMemory": 8,
    "timezone": "America/Los_Angeles",
    "screen": {
        "width": 1280,
        "height": 800,
        "innerWidth": 1280,
        "innerHeight": 800,
        "outerWidth": 1280,
        "outerHeight": 800,
        "devicePixelRatio": 1,
    },
    "chromeObject": True,
    "chromeRuntime": False,
    "plugins": 3,
    "webglVendor": "Google Inc. (NVIDIA)",
    "webglRenderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Direct3D11 vs_5_0 ps_5_0, D3D11)",
}


class SignalPage(FakePage):
    """FakePage with a script-dispatching evaluate, like a real browser would answer."""

    def __init__(self, *, fingerprint=FINGERPRINT, candidate: str = "none", geo: str = "prompt"):
        super().__init__()
        self.fingerprint = fingerprint
        self.candidate = candidate
        self.geo = geo
        self.scripts: list[str] = []

    async def evaluate(self, script: str, arg=None):
        self.scripts.append(script)
        if "navigator.webdriver" in script:
            return self.fingerprint
        if "RTCPeerConnection" in script:
            return self.candidate
        if "navigator.permissions" in script:
            return self.geo
        return True


# ------------------------------------------------------------------ collect_page_signals


async def test_collects_all_signal_groups():
    page = SignalPage(candidate="203.0.113.7", geo="granted")

    signals = await collect_page_signals(page)

    assert signals["webdriver"] is False
    assert signals["platform"] == "Win32"
    assert signals["userAgent"].startswith("Mozilla/5.0")
    assert signals["timezone"] == "America/Los_Angeles"
    assert signals["screen"]["innerWidth"] == 1280
    assert signals["chromeObject"] is True
    assert signals["webglRenderer"].startswith("ANGLE")
    assert signals["webrtcCandidateIp"] == "203.0.113.7"
    assert signals["geolocationPermission"] == "granted"
    assert len(page.scripts) == 3


async def test_empty_ice_candidate_is_reported_as_none():
    page = SignalPage(candidate="none")

    signals = await collect_page_signals(page)

    # "none" is an answer, not a leak: the browser produced no candidate inside the budget.
    assert signals["webrtcCandidateIp"] == "none"


async def test_non_dict_fingerprint_is_wrapped_not_dropped():
    page = SignalPage(fingerprint="error: RuntimeError")

    signals = await collect_page_signals(page)

    assert signals["evaluate"] == "error: RuntimeError"
    assert "webrtcCandidateIp" in signals and "geolocationPermission" in signals


async def test_failing_eval_degrades_to_error_string():
    class Boom(SignalPage):
        async def evaluate(self, script: str, arg=None):
            raise RuntimeError("page crashed")

    signals = await collect_page_signals(Boom())

    assert signals["evaluate"] == "error: RuntimeError"
    assert signals["webrtcCandidateIp"] == "error: RuntimeError"
    assert signals["geolocationPermission"] == "error: RuntimeError"


async def test_slow_eval_is_bounded_by_the_timeout():
    class Hanging(SignalPage):
        async def evaluate(self, script: str, arg=None):
            await asyncio.sleep(30)
            return "never"

    loop = asyncio.get_running_loop()
    started = loop.time()
    signals = await collect_page_signals(
        Hanging(), rtc_budget_ms=50, signal_timeout_s=0.05, rtc_timeout_s=0.05, geo_timeout_s=0.05
    )
    elapsed = loop.time() - started

    assert signals["evaluate"] == "error: TimeoutError"
    assert signals["webrtcCandidateIp"] == "error: TimeoutError"
    assert signals["geolocationPermission"] == "error: TimeoutError"
    assert elapsed < 2.0, f"probe not bounded: {elapsed:.2f}s"


# ---------------------------------------------------------------------- cmd_probe_profile


def _arm_probe(monkeypatch, page: FakePage, gpm: FakeGPM | None = None) -> FakeGPM:
    gpm = gpm or FakeGPM()
    browser = FakeBrowser()

    async def fake_attach(*args, **kwargs):
        browser.page = page
        return browser

    deps = SimpleNamespace(gpm=gpm)

    monkeypatch.setattr("cli._deps", lambda settings: deps)
    monkeypatch.setattr("adapters.browser.attach", fake_attach)
    return gpm


def test_cmd_probe_profile_prints_signals_and_stops_profile(monkeypatch, capsys):
    page = SignalPage(candidate="203.0.113.7", geo="prompt")
    gpm = _arm_probe(monkeypatch, page)

    code = main(["probe-profile", "--profile-id", "p1"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["title"] == "Fake Yelp"
    assert payload["signals"]["platform"] == "Win32"
    assert payload["signals"]["webrtcCandidateIp"] == "203.0.113.7"
    assert payload["signals"]["geolocationPermission"] == "prompt"
    assert gpm.stopped == ["p1"]


def test_cmd_probe_profile_no_signals_skips_evaluate(monkeypatch, capsys):
    page = SignalPage()
    gpm = _arm_probe(monkeypatch, page)

    code = main(["probe-profile", "--profile-id", "p2", "--no-signals"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["signals"] == {}
    assert page.scripts == []
    assert gpm.stopped == ["p2"]


def test_cmd_probe_profile_releases_profile_even_when_eval_fails(monkeypatch, capsys):
    class BrokenPage(SignalPage):
        async def evaluate(self, script: str, arg=None):
            raise RuntimeError("target closed")

    gpm = _arm_probe(monkeypatch, BrokenPage())

    code = main(["probe-profile", "--profile-id", "p3"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["signals"]["evaluate"] == "error: RuntimeError"
    # the GPM profile must be released, otherwise the slot leaks for the whole farm
    assert gpm.stopped == ["p3"]
