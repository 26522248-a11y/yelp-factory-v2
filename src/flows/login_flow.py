"""Login flow S1-S7 (real-world 2026-11-08: password -> passwordless email link).

Steps (spec v3.0 section 4):
  S1 PRECHECK  - a live session skips everything (T-10)
  S2 PASSWORD  - fill the visible login form (T-1) and submit
  S3 CHALLENGE - classify the outcome (T-2): direct / email link / toast / silent
  S4 LINK      - fetch the passwordless link from the mailbox (T-5, T-7, T-8)
  S5 CONFIRM   - open the link in the target profile and press Continue (T-6)
  S6 VERIFY    - owner view "Edit profile" on the account page (T-9)
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.base import YFError
from core.backoff import RetryPolicy
from human.mouse import human_click
from human.typing import human_type
from obs.log import get_logger

log = get_logger("flows.login")

LOGIN_URL = "https://www.yelp.com/login?locale=en_US"
HOME_URL = "https://www.yelp.com/?locale=en_US"
USER_URL = "https://www.yelp.com/user_details?userid={user_id}"

CHALLENGE_NOTICE = "sent an email with a login link"
CHALLENGE_ALT = "confirm it's really you"
BAD_CREDENTIALS = ("doesn't look right", "wrong email or password", "incorrect email")
ERROR_TOAST = "unable to log you in"
CAPTCHA_MARKERS = (
    "hcaptcha",
    "are you a robot",
    "verify you are a human",
    "verify your identity",
    "account under review",
    "suspicious activity",
)
CONFIRM_HEADING = "logging in as"


class LoginError(YFError):
    code = "login_error"


def classify_login_outcome(text: str, *, logged_in: bool) -> str:
    """Map page text + session state to one of the four submit outcomes (T-2)."""
    low = str(text or "").lower()
    if logged_in:
        return "logged_in"
    if any(marker in low for marker in BAD_CREDENTIALS):
        return "bad_credentials"
    if CHALLENGE_NOTICE in low or CHALLENGE_ALT in low:
        return "email_link"
    if ERROR_TOAST in low:
        return "error_toast"
    if any(marker in low for marker in CAPTCHA_MARKERS):
        return "captcha"
    return "pending"


@dataclass(slots=True)
class LoginResult:
    ok: bool
    status: str  # SUCCESS | NEEDS_REVIEW | FAILED
    stage: str
    error_code: str | None = None
    url: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "stage": self.stage,
            "error_code": self.error_code,
            "url": self.url,
            **self.detail,
        }


class LoginFlow:
    """Runs the login sequence against an already-attached browser page."""

    def __init__(
        self,
        *,
        registry,
        settings,
        email_provider=None,
        retry: RetryPolicy | None = None,
    ):
        self.registry = registry
        self.settings = settings
        self.email = email_provider
        self.retry = retry or RetryPolicy(max_attempts=3, base_s=8.0, max_s=45.0)
        self.login_url = settings.login.login_url if settings else LOGIN_URL

    # ------------------------------------------------------------------ public

    async def run(
        self,
        page: Any,
        *,
        email: str,
        password: str,
        user_id: str | None = None,
        alias: str | None = None,
        shot_dir: str | Path | None = None,
    ) -> LoginResult:
        started = time.monotonic()
        shot = _Shotter(page, shot_dir or (Path(self.settings.artifacts_dir) / "login"), email)

        # ---- S1 PRECHECK (T-10)
        from adapters.browser import is_logged_in

        if await is_logged_in(page):
            result = await self._verify(page, user_id=user_id, shot=shot, stage="precheck")
            if result:
                return self._done(result, started, "precheck", "SUCCESS")
            return LoginResult(True, "SUCCESS", "precheck", url=page.url, detail={"already_logged_in": True})

        submit_attempts = 0
        max_attempts = self.settings.login.max_password_attempts if self.settings else 3
        bad_creds_left = self.settings.login.bad_credentials_retries if self.settings else 1
        since: datetime | None = None
        resend_left = self.settings.login.max_resend if self.settings else 2

        while submit_attempts < max_attempts:
            submit_attempts += 1

            # ---- S2 PASSWORD
            since = await self._submit_password(page, email, password, shot)

            # ---- S3 CHALLENGE
            outcome = await self._poll_outcome(page, shot)
            log.info("login_outcome", outcome=outcome, attempt=submit_attempts)

            if outcome == "logged_in":
                result = await self._verify(page, user_id=user_id, shot=shot, stage="verified")
                return self._done(result, started, "verified", "SUCCESS")

            if outcome == "bad_credentials":
                # One wrong-password result can be an autofill/mask artifact; retry once,
                # a third failure just buys a captcha (2026-11-09 review).
                if bad_creds_left > 0:
                    bad_creds_left -= 1
                    log.warning("login_bad_credentials_retry", attempt=submit_attempts)
                    await page.wait_for_timeout(random.randint(4000, 9000))
                    continue
                await shot.dump("bad_credentials")
                return LoginResult(False, "FAILED", "password", error_code="login_bad_credentials", url=page.url)

            if outcome == "captcha":
                # Never die silently on a challenge wall: screenshot + HTML + needs_manual.
                await shot.dump("captcha")
                return LoginResult(
                    False,
                    "NEEDS_REVIEW",
                    "challenge",
                    error_code="login_captcha",
                    url=page.url,
                    detail={"needs_manual": True},
                )

            if outcome == "email_link":
                break

            # error_toast / silent -> back off and retry the submit (T-2c, T-2d)
            delay = self.retry.delay(submit_attempts)
            log.warning("login_retry", attempt=submit_attempts, delay_s=round(delay, 2))
            await page.wait_for_timeout(int(delay * 1000))
        else:
            return LoginResult(False, "NEEDS_REVIEW", "challenge", error_code="login_transient", url=page.url)

        # ---- S4 LINK (T-5, T-7, T-8)
        try:
            link = await self._fetch_link(email or alias or email, since=since, page=page, shot=shot)
        except YFError as exc:
            if resend_left > 0 and await self._resend(page):
                resend_left -= 1
                try:
                    link = await self._fetch_link(email, since=None, page=page, shot=shot)
                except YFError as exc2:
                    return LoginResult(False, "NEEDS_REVIEW", "link", error_code=exc2.code, url=page.url)
            else:
                return LoginResult(False, "NEEDS_REVIEW", "link", error_code=exc.code, url=page.url)

        # ---- S5 CONFIRM (T-6, E-66)
        confirmed = await self._confirm(page, link, shot)
        if not confirmed:
            if resend_left > 0 and await self._resend(page):
                try:
                    link = await self._fetch_link(email, since=None, page=page, shot=shot)
                    confirmed = await self._confirm(page, link, shot)
                except YFError as exc:
                    return LoginResult(False, "NEEDS_REVIEW", "confirm", error_code=exc.code, url=page.url)
            if not confirmed:
                return LoginResult(False, "NEEDS_REVIEW", "confirm", error_code="login_confirm_missing", url=page.url)

        # ---- S6 VERIFY
        result = await self._verify(page, user_id=user_id, shot=shot, stage="verified")
        return self._done(result, started, "verified", "SUCCESS")

    # ------------------------------------------------------------------ stages

    async def _submit_password(self, page, email: str, password: str, shot: "_Shotter") -> datetime:
        try:
            await page.goto(self.login_url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:  # noqa: BLE001
            log.warning("login_goto_failed", error=str(exc)[:150])
        await page.wait_for_timeout(2500)

        email_field = await self.registry.find(page, "login.email", timeout_ms=20_000)
        password_field = await self.registry.find(page, "login.password", timeout_ms=8_000)
        await human_type(email_field, email)
        await human_type(password_field, password)
        await shot.take("password_page")

        submit = await self.registry.find(page, "login.submit", timeout_ms=8_000)
        await human_click(page, submit)
        return datetime.now(timezone.utc)

    async def _poll_outcome(self, page, shot: "_Shotter") -> str:
        """Poll up to login.submit_poll_s; one silent re-click is allowed (E-62)."""
        from adapters.browser import is_logged_in

        poll_s = self.settings.login.submit_poll_s if self.settings else 20
        waited = 0.0
        reclicked = False
        while waited <= poll_s:
            await page.wait_for_timeout(2500)
            waited += 2.5
            try:
                text = await page.evaluate("() => (document.body ? document.body.innerText : '')")
            except Exception:  # noqa: BLE001
                text = ""
            outcome = classify_login_outcome(str(text or ""), logged_in=await is_logged_in(page))
            if outcome != "pending":
                await shot.take(f"outcome_{outcome}")
                return outcome
            # silent submit: re-click once after 8s of nothing (T-2d)
            if waited >= 8 and not reclicked:
                reclicked = True
                submit = await self.registry.find(page, "login.submit", required=False, timeout_ms=3000)
                if submit is not None:
                    log.warning("login_silent_submit_retry")
                    await human_click(page, submit)
        return "pending"

    async def _fetch_link(self, alias: str, *, since: datetime | None, page, shot: "_Shotter") -> str:
        if self.email is None:
            raise LoginError("no mailbox provider for login link", code="mail_channel")
        try:
            mail = await self.email.wait_for_verification(
                alias, timeout_s=self.settings.login.link_timeout_s if self.settings else 120, since=since
            )
        except YFError as exc:
            code = "login_link_timeout" if exc.code in {"no_email", "email_error"} else exc.code
            raise LoginError(str(exc), code=code) from exc
        await shot.take("mail_link")
        return mail.link

    async def _confirm(self, page, link: str, shot: "_Shotter") -> bool:
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:  # noqa: BLE001
            log.warning("passwordless_goto_failed", error=str(exc)[:150])
            return False
        await page.wait_for_timeout(4000)
        await shot.take("passwordless")
        try:
            text = await page.evaluate("() => (document.body ? document.body.innerText : '')")
        except Exception:  # noqa: BLE001
            text = ""
        if CONFIRM_HEADING not in str(text or "").lower():
            return False
        try:
            button = await self.registry.find(page, "passwordless.continue_btn", timeout_ms=8000)
            await human_click(page, button)
        except Exception as exc:  # noqa: BLE001
            log.warning("passwordless_continue_failed", error=str(exc)[:150])
            return False
        await page.wait_for_timeout(5000)
        await shot.take("after_continue")
        return True

    async def _resend(self, page) -> bool:
        try:
            return await self.registry.click(page, "login.resend_link", force_after=1)
        except Exception:  # noqa: BLE001
            return False

    async def _verify(self, page, *, user_id: str | None, shot: "_Shotter", stage: str) -> dict[str, Any]:
        from adapters.browser import is_logged_in

        detail: dict[str, Any] = {}
        if not await is_logged_in(page):
            detail["logged_in"] = False
            return detail
        detail["logged_in"] = True
        verify_owner = self.settings.login.verify_owner if self.settings else True
        if user_id and verify_owner:
            try:
                await page.goto(USER_URL.format(user_id=user_id), wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(4000)
                await shot.take("verify_profile")
                text = await page.evaluate("() => (document.body ? document.body.innerText : '')")
                detail["owner_view"] = "edit profile" in str(text or "").lower()
                if not detail["owner_view"]:
                    await shot.dump("verify_failed")
            except Exception as exc:  # noqa: BLE001
                log.warning("login_verify_failed", error=str(exc)[:150])
                detail["owner_view"] = False
        try:
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001
            pass
        detail["url"] = page.url
        return detail

    @staticmethod
    def _done(detail: dict[str, Any], started: float, stage: str, status: str) -> LoginResult:
        ok = bool(detail.get("logged_in")) and detail.get("owner_view", True)
        return LoginResult(
            ok=ok,
            status=status if ok else "NEEDS_REVIEW",
            stage=stage,
            error_code=None if ok else "login_verify_failed",
            url=detail.get("url", ""),
            detail={k: v for k, v in detail.items() if k != "url"},
        )


class _Shotter:
    """Best-effort screenshots + HTML dumps; never fail a flow because of artifacts (E-71)."""

    def __init__(self, page, directory: str | Path, email: str):
        self.page = page
        self.dir = Path(directory)
        self.tag = re.sub(r"[^a-zA-Z0-9]+", "_", email)[:40]

    async def take(self, name: str) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=str(self.dir / f"{self.tag}_{name}.png"))
        except Exception:  # noqa: BLE001
            pass

    async def dump(self, name: str) -> None:
        """Screenshot + full HTML on failures: debugging NEEDS_MANUAL without them is blind."""
        await self.take(name)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            html = await self.page.content()
            # never persist magic-link tokens or session ids (C7)
            html = re.sub(r"ytl_=[^&\"'<>]+", "ytl_=[redacted]", html)
            html = re.sub(r"MLA[A-Za-z0-9]+", "MLA[redacted]", html)
            (self.dir / f"{self.tag}_{name}.html").write_text(html, encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
