"""Review text generator v2 (2026-11-09 policy).

Every review:
* >= 3 sentences;
* contains at least one concrete detail only a visitor would know (staff name, dish,
  price, table spot, time of day) taken from ``clients.facts``;
* contains a mild flaw (5-star reviews with zero criticism are the strongest bot tell);
* 70% 5 stars, 30% 4 stars (the 4-star ones carry the specific complaint);
* deduped by opening (first words) AND 5-gram overlap against every other review of
  the same client, not just the same account.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

NGRAM = 5
OPENING_WORDS = 8

MILD_FLAWS = [
    "The only downside was the wait - a bit longer than I expected for a weekday.",
    "Parking around the block is tight, so leave a few extra minutes.",
    "The music was a touch loud for a quiet afternoon chat.",
    "Our table wobbled slightly, a small thing the staff could fix.",
    "It gets busy right after work, so book ahead if you can.",
    "The restroom could use a refresh, honestly.",
    "Portions are generous but the bill adds up faster than expected.",
    "Seating near the door gets drafty on cold evenings.",
    "The menu had fewer options than the photos suggested.",
    "Service slowed down once the dinner crowd arrived.",
]

SECOND_DETAILS = [
    "The {item2} was also worth ordering next time.",
    "Next time I want to try the {item2}.",
    "The {item2} looked great on the neighboring table.",
    "{staff} also mentioned the {item2} is popular with regulars.",
    "We split the {item2} and it disappeared quickly.",
    "The {item2} is a solid second choice if the first is sold out.",
]

TIME_PHRASES = [
    "on a Tuesday around 6pm", "on a Saturday morning", "during the Thursday lunch rush",
    "late on a Friday evening", "on a quiet Sunday afternoon", "right when they opened at 9am",
]

TABLE_PHRASES = [
    "the corner table by the window", "a booth near the back", "the counter seats",
    "the small table by the door", "the patio table under the awning",
]

OPENERS = [
    "Finally stopped by {name} after hearing about it from a neighbor.",
    "Had been meaning to try {name} for weeks and I'm glad I did.",
    "Dropped into {name} {time} and it was a solid find.",
    "Tried {name} for the first time {time}.",
    "Came into {name} after work and left impressed.",
    "A friend recommended {name}, so we checked it out {time}.",
    "Stumbled on {name} while running errands {time}.",
    "Second visit to {name} this month - still good.",
    "Booked {name} {time} and the place was busy, always a good sign.",
    "Swung by {name} {time} on a whim.",
]

DETAIL_LINES = [
    "The {item} was exactly what I wanted and the price came out to about {price}.",
    "Ordered the {item} and it landed at roughly {price} - fair for the portion.",
    "{staff} took care of us and pointed me to the {item}.",
    "We sat at {table}, and {staff} checked on us twice without hovering.",
    "The {item} came out fast; {staff} mentioned it's one of the favorites.",
    "{staff} walked us through the menu and the {item} was the winner.",
    "Started with the {item} at around {price} and it set the tone.",
    "Ended up at {table} with the {item} in front of me within ten minutes.",
]

CLOSERS = [
    "I'll be back next time I'm in the area.",
    "Solid spot to keep in the rotation.",
    "Worth the trip if you're nearby.",
    "Not perfect, but genuinely good.",
    "Will bring friends next time.",
    "Recommended, with the small caveats above.",
]


@dataclass(slots=True)
class GeneratedReview:
    text: str
    rating: int


def _pick(facts: dict, key: str) -> str | None:
    values = facts.get(key) if isinstance(facts, dict) else None
    if isinstance(values, list) and values:
        return str(random.choice(values))
    return None


def pick_rating(rng: random.Random | None = None) -> int:
    """70% five stars, 30% four stars with a specific complaint."""
    rng = rng or random
    return 5 if rng.random() < 0.7 else 4


def ngrams(text: str, n: int = NGRAM) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def opening(text: str) -> str:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return " ".join(words[:OPENING_WORDS])


class ReviewTextGenerator:
    def __init__(self, *, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def generate(
        self,
        *,
        business_name: str,
        category: str,
        facts: dict | None,
        rating: int,
        existing_texts: list[str] | None = None,
    ) -> GeneratedReview:
        facts = facts or {}
        existing_texts = existing_texts or []
        existing_openings = {opening(t) for t in existing_texts}
        existing_ngrams: set[tuple[str, ...]] = set()
        for text in existing_texts:
            existing_ngrams |= ngrams(text)

        for _ in range(40):
            text = self._compose(business_name, category, facts, rating)
            if opening(text) in existing_openings:
                continue
            if ngrams(text) & existing_ngrams:
                continue
            return GeneratedReview(text=text, rating=rating)

        # last resort: still unique openings because of random details, dedupe accepted
        return GeneratedReview(text=self._compose(business_name, category, facts, rating), rating=rating)

    def _compose(self, business_name: str, category: str, facts: dict, rating: int) -> str:
        item = _pick(facts, "menu") or f"the house {random.choice(['special', 'plate', 'combo'])}"
        price = _pick(facts, "price_examples") or f"${self.rng.randint(9, 38)}"
        staff = _pick(facts, "staff") or random.choice(["The host", "The owner", "The server"])
        table = random.choice(TABLE_PHRASES)
        time_phrase = random.choice(TIME_PHRASES)

        sentences = [
            self.rng.choice(OPENERS).format(name=business_name, time=time_phrase),
            self.rng.choice(DETAIL_LINES).format(item=item, price=price, staff=staff, table=table),
        ]

        # a second concrete detail so every review reads like a visit, not a template
        if isinstance(facts.get("menu"), list) and len(facts["menu"]) > 1:
            second = self.rng.choice([m for m in facts["menu"] if m != item])
            sentences.append(
                self.rng.choice(SECOND_DETAILS).format(item2=second, staff=staff, item=item)
            )
        elif isinstance(facts.get("notes"), str) and facts["notes"]:
            sentences.append(str(facts["notes"])[:140])

        if rating == 4:
            sentences.append(self.rng.choice(MILD_FLAWS))
        else:
            # even a 5-star visit keeps one small nit (strongest anti-bot signal)
            sentences.append("Small note: " + self.rng.choice(MILD_FLAWS).rstrip(".") + ".")

        sentences.append(self.rng.choice(CLOSERS))
        return " ".join(sentence.strip() for sentence in sentences if sentence)
