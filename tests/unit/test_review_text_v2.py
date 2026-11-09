"""Review text v2 policy: concrete details, mild flaw, opening + 5-gram dedupe."""

from __future__ import annotations

import random
import re

from flows.review_text import ReviewTextGenerator, ngrams, opening, pick_rating

FACTS = {
    "menu": ["tonkotsu ramen", "spicy miso ramen", "gyoza"],
    "staff": ["Mika", "Daniel"],
    "price_examples": ["$18", "$22"],
    "notes": "Counter seating faces the kitchen.",
}


def test_review_has_three_sentences_and_concrete_detail():
    gen = ReviewTextGenerator(rng=random.Random(7))
    review = gen.generate(business_name="Example Ramen House", category="restaurants", facts=FACTS, rating=5)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", review.text.strip()) if s]
    assert len(sentences) >= 3
    assert any(token in review.text for token in ["Mika", "Daniel", "$18", "$22", "ramen", "gyoza", "Counter seating"])
    # every review keeps one mild flaw (anti-bot signal)
    assert "Small note:" in review.text or any(
        marker in review.text.lower() for marker in ("wait", "parking", "music", "wobbl", "busy", "restroom")
    )


def test_four_star_reviews_carry_a_specific_complaint():
    from flows.review_text import MILD_FLAWS

    gen = ReviewTextGenerator(rng=random.Random(3))
    review = gen.generate(business_name="Example Nail Bar", category="beauty", facts=FACTS, rating=4)
    assert review.rating == 4
    assert any(flaw.rstrip(".") in review.text for flaw in MILD_FLAWS)


def test_pick_rating_is_roughly_30_percent_four_star():
    rng = random.Random(42)
    ratings = [pick_rating(rng) for _ in range(300)]
    share = ratings.count(4) / len(ratings)
    assert 0.2 <= share <= 0.4
    assert set(ratings) <= {4, 5}


def test_dedupe_on_opening_and_ngrams():
    gen = ReviewTextGenerator(rng=random.Random(11))
    first = gen.generate(business_name="Example Ramen House", category="restaurants", facts=FACTS, rating=5)
    second = gen.generate(
        business_name="Example Ramen House",
        category="restaurants",
        facts=FACTS,
        rating=5,
        existing_texts=[first.text],
    )
    assert opening(first.text) != opening(second.text)
    assert not (ngrams(first.text) & ngrams(second.text))


def test_generator_survives_empty_facts():
    gen = ReviewTextGenerator(rng=random.Random(5))
    review = gen.generate(business_name="Mystery Spot", category="other", facts={}, rating=5)
    assert len(review.text) > 80
    assert review.rating == 5
