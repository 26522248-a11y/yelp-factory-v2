"""Post-review warm session: 1/day, <=120 min, ladder P0 -> P4, NO review (spec v3.0 §5).

Trust-oriented additions (2026-11-09 review):
* profile completeness: first session fills avatar + city/zip + bio and later sessions
  upload one business photo per session (P1b) - empty profiles get reviews filtered;
* friend requests, not only follows;
* per-account metro: every search carries the account's city so the history stays local;
* human rhythm: two-way scrolling, result filters/sort, new tabs, back navigation,
  early page abandonment, longer random idles.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Callable

from core.post_review import (
    REVIEW_KINDS,
    apply_rate_penalty,
    days_active,
    effective_ratio,
    ladder_plan,
    load_state,
    save_state,
    session_count,
    unlocked_phases_by_session,
)
from human.mouse import human_click
from human.timing import idle
from obs.log import get_logger

log = get_logger("flows.post_review_warm")

# Food is not the only thing on Yelp (2026-11-09): weighted mix 40/20/15/15/10 so four
# accounts never build the same culinary fingerprint.
KEYWORD_MIX: list[tuple[str, int, list[str]]] = [
    ("food", 40, ["coffee", "tacos", "ramen", "brunch", "bbq", "seafood", "pizza", "desserts", "burgers", "sushi"]),
    ("home_services", 20, ["home services", "plumber", "HVAC", "locksmith", "electrician", "dry cleaning", "moving company"]),
    ("auto", 15, ["auto repair", "oil change", "car wash", "tire shop", "mechanic"]),
    ("beauty", 15, ["nail salon", "hair salon", "barber shop", "spa", "waxing"]),
    ("health", 10, ["dentist", "doctor", "chiropractor", "optometrist", "urgent care"]),
]


def choose_keyword(rng: random.Random | None = None) -> str:
    rng = rng or random
    categories = [band[2] for band in KEYWORD_MIX]
    weights = [band[1] for band in KEYWORD_MIX]
    band = rng.choices(categories, weights=weights, k=1)[0]
    return rng.choice(band)


SEARCH_QUERIES = [keyword for _, _, words in KEYWORD_MIX for keyword in words]

SORT_OPTIONS = ["Recommended", "Highest Rated", "Most Reviewed", "Open Now", "Distance"]


class PostReviewWarmRunner:
    def __init__(self, *, registry, settings):
        self.registry = registry
        self.settings = settings
        cfg = settings.post_review
        self.max_seconds = cfg.session_minutes_max * 60
        self.min_seconds = cfg.session_minutes_min * 60
        self.hard_stop_s = cfg.hard_stop_minutes * 60
        self.rest_s = tuple(cfg.rest_between_actions_s)
        self.dwell_s = tuple(cfg.page_dwell_s)
        self.idle_probability = cfg.idle_probability
        self.idle_s = tuple(cfg.idle_s)
        self.abandon_probability = cfg.abandon_probability
        self.new_tab_probability = cfg.new_tab_probability
        self.filter_probability = cfg.filter_probability
        self.upload_photos = cfg.upload_photos_per_session
        self.early_photos = getattr(cfg, "early_session_photos", 3)
        self.geo_center = tuple(getattr(cfg, "geo_center", (40.7128, -74.0060)))
        self.geo_by_city = dict(getattr(cfg, "geo_by_city", {}) or {})

    # ------------------------------------------------------------------ session

    async def run_session(
        self,
        page: Any,
        *,
        account_id=None,
        proxy_ip: str | None = None,
        max_seconds: int | None = None,
        resume_phase: str | None = None,
        city: str | None = None,
        user_id: str | None = None,
        fill_profile: bool = False,
        on_block: Callable[[str], None] | None = None,
        account_tag: str | None = None,
    ) -> dict[str, Any]:
        from db.models import ActionLog, WarmingSession
        from db.session import session_scope

        started = datetime.now(timezone.utc)
        clock_start = time.monotonic()
        if max_seconds is None:
            # random session length (25-90 min) - a fixed daily duration is a bot signature
            chosen = random.randint(self.min_seconds, self.max_seconds)
            budget_s = min(chosen, self.hard_stop_s)
        else:
            budget_s = min(max_seconds, self.hard_stop_s)

        active_days = days_active(account_id) if account_id else 3
        real_sessions = session_count(account_id) if account_id else 5
        state = load_state(account_id) if account_id else {"resume_phase": None, "penalty": {"ratio": 1.0}}
        ratio = effective_ratio(account_id) if account_id else 1.0
        from core.volume import effective_multiplier

        # Volume governor applies to warm actions too (lazy weeks / filter throttle).
        volume = effective_multiplier() if account_id else 1.0
        resume_from = resume_phase or state.get("resume_phase")
        photos_this_session = self.photo_allowance(real_sessions, self.early_photos, self.upload_photos)
        plan = []
        for phase, budget in ladder_plan(resume_from):
            scaled = self._scaled(budget, ratio * volume)
            if "upload_photo" in scaled:
                scaled["upload_photo"] = photos_this_session
            plan.append((phase, scaled))
        unlocked = unlocked_phases_by_session(real_sessions)

        session_id = None
        if account_id:
            with session_scope() as session:
                row = WarmingSession(
                    account_id=account_id,
                    mode="post_review",
                    started_at=started,
                    entry_path="ladder",
                    proxy_ip=proxy_ip,
                    meta={"resume_from": resume_from, "days_active": active_days, "ratio": ratio},
                )
                session.add(row)
                session.flush()
                session_id = row.id

        actions: list[str] = []
        rate_limited = False
        resume_phase: str | None = resume_from

        def log_action(kind: str, target: str | None = None, meta: dict | None = None) -> None:
            if not account_id:
                return
            with session_scope() as session:
                session.add(
                    ActionLog(
                        account_id=account_id,
                        session_id=session_id,
                        kind=kind,
                        target=(target or "")[:300] or None,
                        meta=meta or {"proxy_ip": proxy_ip, "mode": "post_review"},
                    )
                )

        try:
            # First session on a fresh account: make the profile look inhabited.
            if fill_profile and time.monotonic() - clock_start < budget_s:
                status = await self._fill_profile(page, user_id=user_id, city=city, account_tag=account_tag)
                if status:
                    actions.append(status)
                    log_action(status, page.url)

            for phase, block_budget in plan:
                if phase not in unlocked:
                    log.info("post_review_phase_skipped", phase=phase, days_active=active_days)
                    continue
                resume_phase = phase
                if on_block:
                    try:
                        on_block(phase)
                    except Exception:  # noqa: BLE001
                        pass
                if time.monotonic() - clock_start >= budget_s:
                    break
                while self._remaining(block_budget) and time.monotonic() - clock_start < budget_s:
                    if page.is_closed():
                        break
                    kind = self._choose(block_budget)
                    if not kind or kind in REVIEW_KINDS:
                        break
                    block_budget[kind] -= 1
                    try:
                        status = await self._do(page, kind, log_action, city=city, user_id=user_id, account_tag=account_tag)
                    except Exception as exc:  # noqa: BLE001
                        if "429" in str(exc) or "403" in str(exc):
                            rate_limited = True
                            log.warning("post_review_rate_limited", error=str(exc)[:150])
                            break
                        status = f"{kind}_error"
                        log.warning("post_review_action_error", kind=kind, error=str(exc)[:150])
                    if status:
                        actions.append(status)
                    if random.random() < self.idle_probability:
                        await idle(page, low=float(self.idle_s[0]), high=float(self.idle_s[1]))
                    else:
                        await page.wait_for_timeout(random.randint(int(self.rest_s[0] * 1000), int(self.rest_s[1] * 1000)))
                else:
                    # block finished normally -> ladder moves on; clear resume marker
                    resume_phase = None
                    continue
                break  # stopped mid-block (time cap, closed page, rate limit)
        finally:
            elapsed = time.monotonic() - clock_start
            if account_id:
                if rate_limited:
                    apply_rate_penalty(account_id, days=self.settings.post_review.penalty_days_on_429)
                save_state(account_id, resume_phase=resume_phase)
                with session_scope() as session:
                    row = session.get(WarmingSession, session_id)
                    if row is not None:
                        row.ended_at = datetime.now(timezone.utc)
                        row.actions = len(actions)
                        meta = dict(row.meta or {})
                        meta.update({"resume_phase": resume_phase, "rate_limited": rate_limited, "elapsed_s": round(elapsed, 1)})
                        row.meta = meta

        return {
            "mode": "post_review",
            "actions": actions,
            "resume_phase": resume_phase,
            "rate_limited": rate_limited,
            "days_active": active_days,
            "duration_s": round(time.monotonic() - clock_start, 1),
        }

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def photo_allowance(real_sessions: int, early: int, normal: int) -> int:
        """First three sessions upload ``early`` photos; later sessions ``normal``.

        The P1 budget is overridden by this allowance, so 'photo <= 2' in the spec refers
        to PHOTO VIEWS; upload counts are governed here (B4).
        """
        return early if real_sessions < 3 else normal

    @staticmethod
    def _scaled(budget: dict[str, int], ratio: float) -> dict[str, int]:
        if ratio >= 1.0:
            return dict(budget)
        # round with a floor of 1 so a 20-40% weekly cut never silently deletes a rare
        # action (photo upload / check-in) from the schedule
        return {kind: (max(1, round(count * ratio)) if count > 0 and ratio > 0 else 0) for kind, count in budget.items()}

    @staticmethod
    def _remaining(budget: dict[str, int]) -> int:
        return sum(budget.values())

    def _choose(self, budget: dict[str, int]) -> str:
        weights = {
            "pageview": 6, "search": 4, "scroll": 4, "save": 3, "vote": 3,
            "follow": 2, "friend": 2, "photo": 2, "upload_photo": 3, "checkin": 2,
            "browse_menu": 3, "browse_hot_new": 2, "browse_events": 2, "share": 2,
            "react": 3, "ask_question": 2, "answer_question": 2,
            "create_collection": 2, "add_to_collection": 3, "rsvp_event": 2, "filter_advanced": 2,
        }
        choices = [(kind, weight) for kind, weight in weights.items() if budget.get(kind, 0) > 0 and kind not in REVIEW_KINDS]
        if not choices:
            return ""
        kinds = [k for k, _ in choices]
        return random.choices(kinds, weights=[w for _, w in choices], k=1)[0]

    def _city_param(self, city: str | None) -> str:
        if not city:
            return ""
        return f"&find_loc={city.replace(' ', '+').replace(',', '%2C')}"

    # ------------------------------------------------------------------ actions

    async def _do(self, page, kind: str, log, *, city: str | None = None, user_id: str | None = None, account_tag: str | None = None) -> str:
        if kind == "pageview":
            return await self._pageview(page, log, city=city)
        if kind == "search":
            return await self._search(page, log, city=city)
        if kind == "scroll":
            return await self._scroll(page, log)
        if kind == "save":
            button = await self.registry.find(page, "warmup.save_business", required=False, timeout_ms=2500)
            if button is not None:
                await human_click(page, button)
                log("save", page.url)
                return "save"
            return "save_miss"
        if kind == "vote":
            key = random.choice(["warmup.vote_useful", "warmup.vote_funny", "warmup.vote_cool"])
            button = await self.registry.find(page, key, required=False, timeout_ms=2500)
            if button is not None:
                await human_click(page, button)
                log("vote", page.url, {"key": key})
                return "vote"
            return "vote_miss"
        if kind == "follow":
            button = await self.registry.find(page, "warmup.follow", required=False, timeout_ms=2500)
            if button is not None:
                await human_click(page, button)
                log("follow", page.url)
                return "follow"
            return "follow_miss"
        if kind == "friend":
            button = await self.registry.find(page, "warmup.friend", required=False, timeout_ms=2500)
            if button is not None:
                await human_click(page, button)
                log("friend", page.url)
                return "friend"
            return "friend_miss"
        if kind == "photo":
            tab = await self.registry.find(page, "warmup.photo_tab", required=False, timeout_ms=2500)
            if tab is not None:
                await human_click(page, tab)
                await page.wait_for_timeout(random.randint(self.dwell_s[0] * 1000, self.dwell_s[1] * 1000))
                log("photo", page.url)
                return "photo"
            return "photo_miss"
        if kind == "upload_photo":
            return await self._upload_photo(page, log, account_tag=account_tag, city=city)
        if kind == "checkin":
            return await self._checkin(page, log, city=city)
        if kind == "react":
            return await self._react(page, log)
        if kind == "ask_question":
            return await self._ask_question(page, log)
        if kind == "answer_question":
            return await self._answer_question(page, log)
        if kind == "create_collection":
            return await self._create_collection(page, log)
        if kind == "add_to_collection":
            return await self._add_to_collection(page, log)
        if kind == "share":
            return await self._share(page, log)
        if kind == "browse_menu":
            return await self._browse_menu(page, log)
        if kind == "browse_hot_new":
            return await self._browse_hot_new(page, log, city=city)
        if kind == "browse_events":
            return await self._browse_events(page, log)
        if kind == "rsvp_event":
            return await self._rsvp_event(page, log)
        if kind == "filter_advanced":
            return await self._filter_advanced(page, log)
        return ""

    async def _pageview(self, page, log, *, city: str | None = None) -> str:
        query = choose_keyword()
        try:
            await page.goto(f"https://www.yelp.com/search?find_desc={query}{self._city_param(city)}", timeout=45_000)
        except Exception:  # noqa: BLE001
            return "pageview_error"
        await page.wait_for_timeout(random.randint(2_000, 6_000))
        await self._maybe_filter(page)
        await self._scroll(page, log, quiet=True)

        link = await self.registry.find(page, "warmup.result_link", required=False, timeout_ms=3000)
        if link is not None:
            opened_tab = await self._maybe_new_tab(page, link)
            if not opened_tab:
                try:
                    await human_click(page, link)
                    await page.wait_for_load_state("domcontentloaded", timeout=30_000)
                except Exception:  # noqa: BLE001
                    pass

        # 6%: visit only the photo album, skip the review text (a real browsing pattern)
        if random.random() < 0.06:
            photo_tab = await self.registry.find(page, "warmup.photo_tab", required=False, timeout_ms=2000)
            if photo_tab is not None:
                try:
                    await human_click(page, photo_tab)
                    await page.wait_for_timeout(random.randint(3_000, 8_000))
                except Exception:  # noqa: BLE001
                    pass
            log("pageview_photos_only", page.url, {"query": query})
            return "pageview_photos"

        if random.random() < self.abandon_probability:
            # leave early like a human who changed their mind
            await page.wait_for_timeout(random.randint(2_000, 5_000))
            try:
                await page.go_back()
            except Exception:  # noqa: BLE001
                pass
        else:
            await page.wait_for_timeout(random.randint(self.dwell_s[0] * 1000, self.dwell_s[1] * 1000))
            await self._scroll(page, log, quiet=True)
            if random.random() < 0.4:
                try:
                    await page.go_back()
                    if random.random() < 0.25:
                        await page.wait_for_timeout(random.randint(800, 2_000))
                        await page.go_back()  # double back is common on mobile
                except Exception:  # noqa: BLE001
                    pass
        log("pageview", page.url, {"query": query, "city": city})
        return "pageview"

    async def _search(self, page, log, *, city: str | None = None) -> str:
        box = await self.registry.find(page, "warmup.search", required=False, timeout_ms=3000)
        if box is None:
            return "search_miss"
        await box.fill(choose_keyword())
        await box.press("Enter")
        await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        await self._maybe_filter(page)
        log("search", page.url)
        return "search"

    async def _scroll(self, page, log, *, quiet: bool = False) -> str:
        # humans scroll up again - always scrolling down is a bot tell
        direction = random.choice([1, 1, 1, -1])
        if random.random() < 0.12:
            # occasional rapid flick then a pause (phone-thumb behaviour)
            for _ in range(random.randint(2, 4)):
                await page.mouse.wheel(0, direction * random.randint(700, 1400))
                await page.wait_for_timeout(random.randint(60, 180))
            await page.wait_for_timeout(random.randint(2_000, 5_000))
        else:
            bursts = random.randint(1, 3)
            for _ in range(bursts):
                await page.mouse.wheel(0, direction * random.randint(150, 700))
                await page.wait_for_timeout(random.randint(400, 1800))
        if not quiet:
            log("scroll", page.url, {"direction": "down" if direction > 0 else "up"})
            return "scroll"
        return "scroll"

    def _geo_for(self, city: str | None) -> tuple[float, float]:
        if city:
            key = city.split(",")[0].strip().lower()
            if key in self.geo_by_city:
                return tuple(self.geo_by_city[key])
        return self.geo_center

    async def _checkin(self, page, log, *, city: str | None = None) -> str:
        """Check-in on the business page with borough coordinates pushed per session.

        The geolocation permission is already granted at profile-create time
        (``geolocation_mode=1`` = Allow), so no ``grant_permissions`` CDP call is
        needed here any more: it is redundant and it mutates the permission state
        mid-session, which is exactly the kind of artefact a bot check looks at.
        Coordinates still have to be pushed every session: the GPM create API has
        no lat/lon field.
        """
        try:
            context = getattr(page, "context", None)
            if context is not None and hasattr(context, "set_geolocation"):
                try:
                    base_lat, base_lon = self._geo_for(city)
                    # 200-300 m scatter inside the account's own borough (C1)
                    lat = base_lat + random.uniform(-0.003, 0.003)
                    lon = base_lon + random.uniform(-0.003, 0.003)
                    await context.set_geolocation({"latitude": lat, "longitude": lon})
                except Exception as exc:  # noqa: BLE001
                    log.warning("checkin_geolocation_failed", error=str(exc)[:120])
            button = await self.registry.find(page, "warmup.checkin", required=False, timeout_ms=3000)
            if button is None:
                return "checkin_miss"
            await human_click(page, button)
            await page.wait_for_timeout(random.randint(1_500, 3_000))
            log("checkin", page.url)
            return "checkin"
        except Exception as exc:  # noqa: BLE001
            log.warning("checkin_error", error=str(exc)[:150])
            return "checkin_error"

    # ------------------------------------------------------------------ new actions

    async def _react(self, page, log) -> str:
        """React to a review: Helpful, Thanks, Love this, Oh no."""
        reaction_keys = ["warmup.react_helpful", "warmup.react_thanks", "warmup.react_love", "warmup.react_ohno"]
        key = random.choice(reaction_keys)
        button = await self.registry.find(page, key, required=False, timeout_ms=2000)
        if button is not None:
            await human_click(page, button)
            log("react", page.url, {"key": key})
            return "react"
        return "react_miss"

    async def _ask_question(self, page, log) -> str:
        """Ask a question in the Q&A section on a business page."""
        trigger = await self.registry.find(page, "warmup.ask_question_trigger", required=False, timeout_ms=2500)
        if trigger is None:
            return "ask_question_miss"
        await human_click(page, trigger, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(1_500, 3_000))
        box = await self.registry.find(page, "warmup.ask_question_input", required=False, timeout_ms=2500)
        if box is None:
            return "ask_question_no_input"
        questions = [
            "Do they take reservations on weekends?",
            "Is there parking nearby?",
            "Are there vegan options?",
            "What are the happy hour times?",
            "Do they offer delivery?",
        ]
        await box.fill(random.choice(questions))
        await page.wait_for_timeout(random.randint(1_000, 2_000))
        submit = await self.registry.find(page, "warmup.ask_question_submit", required=False, timeout_ms=2000)
        if submit is not None:
            await human_click(page, submit, dwell=(200, 400))
            await page.wait_for_timeout(random.randint(2_000, 4_000))
        log("ask_question", page.url)
        return "ask_question"

    async def _answer_question(self, page, log) -> str:
        """Answer someone's question in the Q&A section."""
        answer_link = await self.registry.find(page, "warmup.answer_question_link", required=False, timeout_ms=2500)
        if answer_link is None:
            return "answer_question_miss"
        await human_click(page, answer_link, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(1_500, 3_000))
        box = await self.registry.find(page, "warmup.answer_question_input", required=False, timeout_ms=2500)
        if box is None:
            return "answer_question_no_input"
        answers = [
            "Yes, they do take reservations, I called ahead last time.",
            "There's a parking garage across the street, pretty reasonable.",
            "They have a few vegan dishes, the salads are great.",
            "Happy hour is usually 3-6pm on weekdays.",
            "Yes, they deliver through their own app and third-party services.",
        ]
        await box.fill(random.choice(answers))
        await page.wait_for_timeout(random.randint(1_000, 2_000))
        submit = await self.registry.find(page, "warmup.answer_question_submit", required=False, timeout_ms=2000)
        if submit is not None:
            await human_click(page, submit, dwell=(200, 400))
            await page.wait_for_timeout(random.randint(2_000, 4_000))
        log("answer_question", page.url)
        return "answer_question"

    async def _create_collection(self, page, log) -> str:
        """Create a new collection (business bookmark folder)."""
        trigger = await self.registry.find(page, "warmup.create_collection_trigger", required=False, timeout_ms=2500)
        if trigger is None:
            return "create_collection_miss"
        await human_click(page, trigger, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(1_500, 3_000))
        box = await self.registry.find(page, "warmup.create_collection_name", required=False, timeout_ms=2500)
        if box is None:
            return "create_collection_no_input"
        collection_names = [
            "Weekend Brunch Spots",
            "Date Night Places",
            "Quick Lunch Ideas",
            "Coffee Shops to Try",
            "Places for Groups",
        ]
        await box.fill(random.choice(collection_names))
        await page.wait_for_timeout(random.randint(1_000, 2_000))
        submit = await self.registry.find(page, "warmup.create_collection_submit", required=False, timeout_ms=2000)
        if submit is not None:
            await human_click(page, submit, dwell=(200, 400))
            await page.wait_for_timeout(random.randint(2_000, 4_000))
        log("create_collection", page.url)
        return "create_collection"

    async def _add_to_collection(self, page, log) -> str:
        """Add current business to an existing collection."""
        button = await self.registry.find(page, "warmup.save_to_collection", required=False, timeout_ms=2500)
        if button is None:
            return "add_to_collection_miss"
        await human_click(page, button, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(1_500, 3_000))
        collection_option = await self.registry.find(page, "warmup.collection_option", required=False, timeout_ms=2000)
        if collection_option is not None:
            await human_click(page, collection_option, dwell=(150, 350))
            await page.wait_for_timeout(random.randint(1_000, 2_000))
        confirm = await self.registry.find(page, "warmup.collection_confirm", required=False, timeout_ms=2000)
        if confirm is not None:
            await human_click(page, confirm, dwell=(200, 400))
            await page.wait_for_timeout(random.randint(1_500, 3_000))
        log("add_to_collection", page.url)
        return "add_to_collection"

    async def _share(self, page, log) -> str:
        """Share the current page (copy link)."""
        share_button = await self.registry.find(page, "warmup.share_button", required=False, timeout_ms=2500)
        if share_button is None:
            return "share_miss"
        await human_click(page, share_button, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(1_500, 2_500))
        copy_link = await self.registry.find(page, "warmup.share_copy_link", required=False, timeout_ms=2000)
        if copy_link is not None:
            await human_click(page, copy_link, dwell=(150, 350))
            await page.wait_for_timeout(random.randint(1_000, 2_000))
        log("share", page.url)
        return "share"

    async def _browse_menu(self, page, log) -> str:
        """View the menu tab on a business page."""
        menu_tab = await self.registry.find(page, "warmup.menu_tab", required=False, timeout_ms=2500)
        if menu_tab is None:
            return "browse_menu_miss"
        await human_click(page, menu_tab, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(self.dwell_s[0] * 1000, self.dwell_s[1] * 1000))
        await self._scroll(page, log, quiet=True)
        log("browse_menu", page.url)
        return "browse_menu"

    async def _browse_hot_new(self, page, log, *, city: str | None = None) -> str:
        """Browse Hot & New Businesses section."""
        try:
            await page.goto(
                f"https://www.yelp.com/hotandnew{self._city_param(city)}",
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            await page.wait_for_timeout(random.randint(2_000, 5_000))
            await self._scroll(page, log, quiet=True)
            link = await self.registry.find(page, "warmup.result_link", required=False, timeout_ms=3000)
            if link is not None:
                await human_click(page, link)
                await page.wait_for_load_state("domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(random.randint(self.dwell_s[0] * 1000, self.dwell_s[1] * 1000))
                try:
                    await page.go_back()
                except Exception:  # noqa: BLE001
                    pass
            log("browse_hot_new", page.url, {"city": city})
            return "browse_hot_new"
        except Exception as exc:  # noqa: BLE001
            log.warning("browse_hot_new_error", error=str(exc)[:150])
            return "browse_hot_new_error"

    async def _browse_events(self, page, log) -> str:
        """Browse Yelp Events page."""
        try:
            await page.goto("https://www.yelp.com/events", wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(random.randint(2_000, 5_000))
            await self._scroll(page, log, quiet=True)
            log("browse_events", page.url)
            return "browse_events"
        except Exception as exc:  # noqa: BLE001
            log.warning("browse_events_error", error=str(exc)[:150])
            return "browse_events_error"

    async def _rsvp_event(self, page, log) -> str:
        """RSVP to a Yelp event."""
        rsvp_button = await self.registry.find(page, "warmup.rsvp_button", required=False, timeout_ms=2500)
        if rsvp_button is None:
            return "rsvp_event_miss"
        await human_click(page, rsvp_button, dwell=(200, 500))
        await page.wait_for_timeout(random.randint(1_500, 3_000))
        confirm = await self.registry.find(page, "warmup.rsvp_confirm", required=False, timeout_ms=2000)
        if confirm is not None:
            await human_click(page, confirm, dwell=(200, 400))
            await page.wait_for_timeout(random.randint(2_000, 4_000))
        log("rsvp_event", page.url)
        return "rsvp_event"

    async def _filter_advanced(self, page, log) -> str:
        """Use advanced filters: Cash Back, Price, Distance, Open Now, Rating."""
        if random.random() >= self.filter_probability:
            return "filter_advanced_skipped"
        try:
            trigger = await self.registry.find(page, "warmup.filter_trigger", required=False, timeout_ms=2000)
            if trigger is None:
                return "filter_advanced_miss"
            await human_click(page, trigger, dwell=(200, 500))
            await page.wait_for_timeout(random.randint(800, 1_800))
            filter_options = ["warmup.filter_cash_back", "warmup.filter_price", "warmup.filter_distance", "warmup.filter_rating"]
            chosen = random.choice(filter_options)
            option = await self.registry.find(page, chosen, required=False, timeout_ms=2000)
            if option is not None:
                await human_click(page, option, dwell=(150, 350))
                await page.wait_for_timeout(random.randint(1_500, 3_000))
            apply_btn = await self.registry.find(page, "warmup.filter_apply", required=False, timeout_ms=2000)
            if apply_btn is not None:
                await human_click(page, apply_btn, dwell=(200, 400))
                await page.wait_for_timeout(random.randint(2_000, 4_000))
            log("filter_advanced", page.url, {"filter": chosen})
            return "filter_advanced"
        except Exception as exc:  # noqa: BLE001
            log.warning("filter_advanced_error", error=str(exc)[:150])
            return "filter_advanced_error"

    async def _maybe_filter(self, page) -> None:
        """Sort/filter the result list - the most human action on a Yelp search page."""
        if random.random() >= self.filter_probability:
            return
        try:
            trigger = await self.registry.find(page, "warmup.sort", required=False, timeout_ms=2000)
            if trigger is None:
                return
            await human_click(page, trigger, dwell=(200, 500))
            await page.wait_for_timeout(random.randint(800, 1800))
            option = random.choice(SORT_OPTIONS)
            choice = page.get_by_text(option, exact=False).first
            if await choice.count():
                await choice.click(timeout=2500)
                await page.wait_for_timeout(random.randint(1_500, 3_500))
        except Exception:  # noqa: BLE001
            return

    async def _maybe_new_tab(self, page, link) -> bool:
        """Open a listing in a second tab now and then (multi-tab browsing pattern)."""
        if random.random() >= self.new_tab_probability:
            return False
        context = getattr(page, "context", None)
        if context is None or not hasattr(link, "get_attribute"):
            return False
        try:
            href = await link.get_attribute("href")
            if not href:
                return False
            url = href if href.startswith("http") else f"https://www.yelp.com{href}"
            tab = await context.new_page()
            await tab.goto(url, wait_until="domcontentloaded", timeout=45_000)
            await tab.wait_for_timeout(random.randint(self.dwell_s[0] * 1000, self.dwell_s[1] * 1000))
            await tab.close()
            await page.bring_to_front()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _upload_photo(self, page, log, *, account_tag: str | None = None, city: str | None = None) -> str:
        """P1b: upload one real-looking business photo (profile completeness = trust).

        Batch 2: photo is GPS-tagged with account's metro coordinates (trust signal).
        """
        try:
            from core.photo_pool import pick_photo

            # batch 2: GPS-tag the photo with the account's metro coordinates
            gps_lat, gps_lon = None, None
            if city:
                base_lat, base_lon = self._geo_for(city)
                # scatter 200-500m for realistic phone GPS accuracy
                gps_lat = base_lat + random.uniform(-0.005, 0.005)
                gps_lon = base_lon + random.uniform(-0.005, 0.005)

            photo = pick_photo("restaurant food", account_tag=account_tag, gps_lat=gps_lat, gps_lon=gps_lon)
            if photo is None:
                return "upload_photo_pool_empty"

            trigger = await self.registry.find(page, "warmup.upload_photo", required=False, timeout_ms=2500)
            if trigger is not None:
                await human_click(page, trigger, dwell=(200, 500))
                await page.wait_for_timeout(random.randint(1_000, 2_000))
            file_input = await self.registry.find(page, "warmup.file_input", required=False, timeout_ms=3000)
            if file_input is None:
                return "upload_photo_miss"
            await file_input.set_input_files(str(photo))
            await page.wait_for_timeout(random.randint(2_000, 4_000))
            submit = await self.registry.find(page, "warmup.upload_submit", required=False, timeout_ms=1500)
            if submit is not None:
                await human_click(page, submit, dwell=(200, 500))
                await page.wait_for_timeout(random.randint(2_000, 5_000))
            log("upload_photo", page.url, {"file": photo.name, "gps": f"{gps_lat:.4f},{gps_lon:.4f}" if gps_lat else None})
            return "upload_photo"
        except Exception as exc:  # noqa: BLE001
            log.warning("upload_photo_error", error=str(exc)[:150])
            return "upload_photo_error"

    async def _fill_profile(self, page, *, user_id: str | None, city: str | None, account_tag: str | None = None) -> str:
        """First session: avatar + city/zip + bio so the profile is not a hollow shell."""
        from core.photo_pool import pick_avatar

        try:
            if not user_id:
                return "profile_skipped_no_user_id"
            await page.goto(f"https://www.yelp.com/user_details?userid={user_id}", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3000)
            edit = await self.registry.find(page, "verify.owner_marker", required=False, timeout_ms=4000)
            if edit is None:
                return "profile_edit_missing"
            await human_click(page, edit, dwell=(300, 700))
            await page.wait_for_timeout(random.randint(2_500, 4_500))

            # avatar
            changed = False
            avatar = pick_avatar(account_tag=account_tag)
            if avatar is not None:
                file_input = await self.registry.find(page, "profile.avatar_input", required=False, timeout_ms=3000)
                if file_input is not None:
                    await file_input.set_input_files(str(avatar))
                    await page.wait_for_timeout(random.randint(1_500, 3_000))
                    changed = True

            # city / zip / about (only fill what exists and is empty)
            filled_city = await self._fill_if_empty(page, "profile.city", city or "")
            if filled_city:
                changed = True
            else:
                if await self._fill_if_empty(page, "profile.zip", ""):
                    changed = True
            if await self._fill_if_empty(page, "profile.about", self._bio_text()):
                changed = True

            if not changed:
                return "profile_nochange"

            save = await self.registry.find(page, "profile.save", required=False, timeout_ms=2500)
            if save is not None:
                await human_click(page, save, dwell=(300, 700))
                await page.wait_for_timeout(random.randint(2_000, 4_000))

            # verify instead of trusting the click: an avatar image must render now
            verified = False
            try:
                avatar_img = await page.locator("img[src*='user_photos'], img[class*='avatar']").first.count()
                verified = bool(avatar_img)
            except Exception:  # noqa: BLE001
                verified = False
            return "profile_filled" if verified else "profile_saved_unverified"
        except Exception as exc:  # noqa: BLE001
            log.warning("profile_fill_error", error=str(exc)[:150])
            return "profile_fill_error"

    async def _fill_if_empty(self, page, key: str, value: str) -> bool:
        if not value:
            return False
        element = await self.registry.find(page, key, required=False, timeout_ms=2000)
        if element is None:
            return False
        try:
            current = await element.input_value()
            if (current or "").strip():
                return False
        except Exception:  # noqa: BLE001
            pass
        try:
            await element.fill(value)
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _bio_text() -> str:
        openers = [
            "Local explorer - coffee, tacos and the occasional home project.",
            "Weekend foodie, weekday DIY. Always looking for good local spots.",
            "New to the neighborhood, trying everything once.",
            "Small business fan. Coffee first, questions later.",
        ]
        return random.choice(openers)
