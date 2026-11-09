"""ReviewPoster failure paths: every blocking condition must return posted=False."""

from __future__ import annotations

from pathlib import Path

import pytest

from flows.review_phase import ReviewPoster
from selector_registry.resolver import SelectorRegistry, SelectorRule
from tests.fakes import FakePage

pytestmark = pytest.mark.asyncio

TEXTAREA = "textarea[name='review']"
SUBMIT = "button[type='submit'][name='submit-review']"
FILE_INPUT = "input[type='file']"

REGISTRY = SelectorRegistry(
    {
        "warmup.review_text": [SelectorRule("css", TEXTAREA, 1)],
        "warmup.review_submit": [SelectorRule("css", SUBMIT, 1)],
        "warmup.review_photo_input": [SelectorRule("css", FILE_INPUT, 1)],
        "warmup.file_input": [SelectorRule("css", FILE_INPUT, 2)],
    }
)


def _poster(settings):
    return ReviewPoster(registry=REGISTRY, settings=settings)


async def test_missing_textarea_blocks_posting(settings, monkeypatch):
    import core.photo_pool as pool

    monkeypatch.setattr("flows.review_phase.pick_photo", lambda *a, **k: None)
    page = FakePage(url="https://www.yelp.com/biz/example")
    result = await _poster(settings).post(
        page,
        business_name="Example Diner",
        yelp_biz_id="example",
        category="restaurants",
        facts={"menu": ["eggs"], "price_examples": ["$9"]},
    )
    assert result["posted"] is False
    assert result["reason"] == "review_textarea_missing"


async def test_missing_photo_input_blocks_posting(settings, monkeypatch, tmp_path):
    import core.photo_pool as pool

    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"jpg")
    monkeypatch.setattr("flows.review_phase.pick_photo", lambda *a, **k: photo)
    page = FakePage(url="https://www.yelp.com/biz/example")
    page.add(TEXTAREA, visible=True)
    result = await _poster(settings).post(
        page,
        business_name="Example Diner",
        yelp_biz_id="example",
        category="restaurants",
        facts={"menu": ["eggs"], "price_examples": ["$9"]},
    )
    assert result["posted"] is False
    assert result["reason"] == "photo_upload_failed"


async def test_missing_submit_blocks_posting(settings, monkeypatch, tmp_path):
    import core.photo_pool as pool

    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"jpg")
    monkeypatch.setattr("flows.review_phase.pick_photo", lambda *a, **k: photo)
    page = FakePage(url="https://www.yelp.com/biz/example")
    page.add(TEXTAREA, visible=True)
    page.add(FILE_INPUT, visible=True)
    result = await _poster(settings).post(
        page,
        business_name="Example Diner",
        yelp_biz_id="example",
        category="restaurants",
        facts={"menu": ["eggs"], "price_examples": ["$9"]},
    )
    assert result["posted"] is False
    assert result["reason"] == "review_submit_missing"


async def test_missing_confirmation_after_submit_is_not_success(settings, monkeypatch, tmp_path):
    import core.photo_pool as pool

    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"jpg")
    monkeypatch.setattr("flows.review_phase.pick_photo", lambda *a, **k: photo)
    page = FakePage(url="https://www.yelp.com/biz/example")
    page.add(TEXTAREA, visible=True)
    page.add(FILE_INPUT, visible=True)
    page.add(SUBMIT, visible=True)
    result = await _poster(settings).post(
        page,
        business_name="Example Diner",
        yelp_biz_id="example",
        category="restaurants",
        facts={"menu": ["eggs"], "price_examples": ["$9"]},
    )
    # the fake page never removes the form, so the poster must not claim success
    assert result["posted"] is False
    assert result["reason"] == "no_confirmation"
    assert result["rating"] in (4, 5)
    assert len(result["text"].split(".")) >= 3

