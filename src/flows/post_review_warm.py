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
            "pageview": 5, "search": 3, "scroll": 3, "save": 2, "vote": 2,
            "follow": 1, "friend": 2, "photo": 1, "upload_photo": 2, "checkin": 1,
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
            return await self._upload_photo(page, log, account_tag=account_tag)
        if kind == "checkin":
            return await self._checkin(page, log, city=city)
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

    async def _upload_photo(self, page, log, *, account_tag: str | None = None) -> str:
        """P1b: upload one real-looking business photo (profile completeness = trust)."""
        try:
            from core.photo_pool import pick_photo

            photo = pick_photo("restaurant food", account_tag=account_tag)
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
            log("upload_photo", page.url, {"file": photo.name})
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
