"""Unit tests for upload_photo step in normal warm flow."""

from __future__ import annotations

import random
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.budget import DailyBudget
from flows.warmup import WarmingRunner
from selector_registry.resolver import SelectorRegistry, SelectorRule
from tests.fakes import FakePage

pytestmark = pytest.mark.asyncio

REGISTRY = SelectorRegistry(
    {
        "warmup.upload_photo": [SelectorRule("css", "button.add-photo", 1)],
        "warmup.file_input": [SelectorRule("css", "input[type='file']", 1)],
        "warmup.upload_submit": [SelectorRule("css", "button.submit-photo", 1)],
    }
)


def _runner():
    return WarmingRunner(gpm=None, registry=REGISTRY, settings=MagicMock())


def _budget() -> DailyBudget:
    return DailyBudget.for_phase("P1")


def _ctx():
    ctx = MagicMock()
    ctx.account_id = None
    ctx.account_tag = None
    ctx.data = {}
    return ctx


@pytest.fixture(autouse=True)
def _fixed_photo_pool(monkeypatch, tmp_path: Path):
    photo = tmp_path / "food.jpg"
    photo.write_bytes(b"fake")

    def fake_pick(category, *, account_tag=None):
        return photo

    import core.photo_pool as pool

    monkeypatch.setattr(pool, "pick_photo", fake_pick)


async def test_upload_photo_happy_path():
    runner = _runner()
    page = FakePage(url="https://www.yelp.com/biz/some-biz")
    page.add("button.add-photo", visible=True)
    page.add("input[type='file']", visible=True)
    page.add("button.submit-photo", visible=True)

    actions = []
    def log(kind, target=None, meta=None):
        actions.append(kind)

    result = await runner._do_upload_photo(page, _ctx(), log)
    assert result == "upload_photo"
    assert "upload" in [e[0] for e in page.events]
    assert "upload_photo" in actions


async def test_upload_photo_miss_when_input_missing():
    runner = _runner()
    page = FakePage(url="https://www.yelp.com/biz/some-biz")
    page.add("button.add-photo", visible=True)

    result = await runner._do_upload_photo(page, _ctx(), lambda *a, **k: None)
    assert result == "upload_photo_miss"


async def test_upload_photo_pool_empty(monkeypatch):
    import core.photo_pool as pool

    monkeypatch.setattr(pool, "pick_photo", lambda *a, **k: None)
    runner = _runner()
    page = FakePage()

    result = await runner._do_upload_photo(page, _ctx(), lambda *a, **k: None)
    assert result == "upload_photo_pool_empty"


async def test_upload_photo_is_chosen_when_allowed_and_budgeted():
    runner = _runner()
    budget = _budget()
    allowed = {"pageview", "search", "save", "upload_photo"}
    random.seed(0)
    choices = {runner._choose_action(budget, allowed, "P1") for _ in range(200)}
    assert "upload_photo" in choices


async def test_upload_photo_not_chosen_without_budget():
    runner = _runner()
    budget = DailyBudget(budget={"pageview": 1, "upload_photo": 0})
    allowed = {"pageview", "upload_photo"}
    for _ in range(20):
        assert runner._choose_action(budget, allowed, "P1") == "pageview"
