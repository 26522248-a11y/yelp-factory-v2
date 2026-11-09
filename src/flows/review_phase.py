"""Review posting flow (2026-11-09 policy): stars + unique text + mandatory photo."""

from __future__ import annotations

import random
import uuid
from typing import Any

from core.photo_pool import pick_photo
from flows.review_text import ReviewTextGenerator, pick_rating
from human.mouse import human_click
from human.typing import human_type
from obs.log import get_logger

log = get_logger("flows.review")

BIZ_URL = "https://www.yelp.com/biz/{biz_id}"


class ReviewPoster:
    def __init__(self, *, registry, settings):
        self.registry = registry
        self.settings = settings
        self.generator = ReviewTextGenerator()

    async def post(
        self,
        page: Any,
        *,
        business_name: str,
        yelp_biz_id: str,
        category: str,
        facts: dict | None,
        existing_texts: list[str] | None = None,
    ) -> dict:
        rating = pick_rating()
        review = self.generator.generate(
            business_name=business_name,
            category=category,
            facts=facts,
            rating=rating,
            existing_texts=existing_texts or [],
        )

        await page.goto(BIZ_URL.format(biz_id=yelp_biz_id), wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(random.randint(2_500, 5_000))

        cta = await self.registry.find(page, "warmup.review_cta", required=False, timeout_ms=5000)
        if cta is not None:
            await human_click(page, cta)
            await page.wait_for_timeout(random.randint(2_000, 4_000))

        # stars
        stars = page.locator("div[role='radiogroup'] button[aria-label*='star']")
        try:
            if await stars.count():
                await stars.nth(min(rating, 5) - 1).click()
                await page.wait_for_timeout(random.randint(700, 1_600))
        except Exception:  # noqa: BLE001
            log.warning("review_stars_miss")

        textarea = await self.registry.find(page, "warmup.review_text", required=False, timeout_ms=5000)
        if textarea is None:
            return {"posted": False, "reason": "review_textarea_missing", "rating": rating, "text": review.text}
        await human_type(textarea, review.text)
        await page.wait_for_timeout(random.randint(1_000, 2_500))

        # photo is mandatory: a review without an upload is a weak review
        photo = pick_photo(f"restaurant {category}")
        photo_attached = False
        if photo is not None:
            file_input = await self.registry.find(page, "warmup.review_photo_input", required=False, timeout_ms=4000)
            if file_input is None:
                file_input = await self.registry.find(page, "warmup.file_input", required=False, timeout_ms=2000)
            if file_input is not None:
                try:
                    await file_input.set_input_files(str(photo))
                    await page.wait_for_timeout(random.randint(2_000, 4_500))
                    photo_attached = True
                except Exception as exc:  # noqa: BLE001
                    log.warning("review_photo_upload_failed", error=str(exc)[:150])
        if not photo_attached:
            return {"posted": False, "reason": "photo_upload_failed", "rating": rating, "text": review.text}

        submit = await self.registry.find(page, "warmup.review_submit", required=False, timeout_ms=4000)
        if submit is None:
            return {"posted": False, "reason": "review_submit_missing", "rating": rating, "text": review.text}
        await human_click(page, submit)
        await page.wait_for_timeout(random.randint(3_000, 6_000))

        body = ""
        try:
            body = (await page.evaluate("() => (document.body ? document.body.innerText : '')")).lower()
        except Exception:  # noqa: BLE001
            pass
        if "review" in body and ("posted" in body or "submitted" in body or "thank" in body):
            return {"posted": True, "rating": rating, "text": review.text, "photo": photo.name}
        # No explicit confirmation: the review form usually disappears on success.
        form_gone = await self.registry.find(page, "warmup.review_text", required=False, timeout_ms=1500) is None
        return {
            "posted": form_gone,
            "rating": rating,
            "text": review.text,
            "photo": photo.name,
            "reason": None if form_gone else "no_confirmation",
        }

    async def is_filtered(self, page: Any, *, yelp_biz_id: str, snippet: str) -> bool:
        """After 72h: does our review still show on the public business page?"""
        await page.goto(
            BIZ_URL.format(biz_id=yelp_biz_id) + "?sort_by=date_desc",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await page.wait_for_timeout(random.randint(2_500, 4_500))
        try:
            body = (await page.evaluate("() => (document.body ? document.body.innerText : '')")).lower()
        except Exception:  # noqa: BLE001
            return False
        key = " ".join(snippet.lower().split()[:10])
        return key not in body
