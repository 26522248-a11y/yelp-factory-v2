"""Orchestrator: one account, one job, one lock (sections 3 and 11)."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from adapters.base import YFError
from core.checkpoints import CheckpointStore, close_run, load_account, open_run, persist_account_state
from core.config import Settings
from core.crypto import SecretBox
from core.lock import AccountLockManager
from core.state_machine import StageContext, StateMachine
from db.models import Account, AccountState, Profile, Quarantine, Run, RunState
from db.session import session_scope
from flows.pools import build_persona
from core.fingerprint_matrix import window_size_for_profile
from flows.signup import SignupFlow
from obs.log import bind_context, get_logger
from obs.metrics import signup_duration_seconds, signup_total

log = get_logger("orchestrator")


@dataclass
class SignupDeps:
    settings: Settings
    gpm: object
    registry: object
    email: object
    captcha: object
    sms: object = None
    artifacts: object = None


def create_account(
    city: str,
    domain: str,
    *,
    box: SecretBox | None = None,
    source: str = "auto",
    max_per_proxy: int = 2,
    probe_city: bool = False,
    batch_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create one account row. ``source`` chooses generated vs imported email/proxy."""
    from core.pool import reserve_email, reserve_proxy

    box = box or SecretBox()
    account_id = uuid.uuid4()
    pool_email = None
    pool_proxy = None
    if source in ("pool_email", "pool_both"):
        pool_email = reserve_email(account_id)
        if pool_email is None:
            raise RuntimeError("pool_exhausted:email")
    if source in ("pool_both", "pool_proxy"):
        pool_proxy = reserve_proxy(account_id, max_per_proxy=max_per_proxy)
        if pool_proxy is None:
            from core.pool import release_email

            if pool_email is not None:
                release_email(pool_email.id)
            raise RuntimeError("pool_exhausted:proxy")

    if pool_proxy is not None and probe_city:
        # The persona city/ZIP must match the exit IP or Yelp rejects the address.
        from adapters.proxysession import rotate_session
        from core.pool import proxy_raw
        from flows.geo import resolve_target_city

        try:
            sticky = rotate_session(proxy_raw(pool_proxy), str(account_id))
            city, _ = asyncio.run(resolve_target_city(sticky, fallback=city, country="US"))
        except Exception as exc:  # noqa: BLE001 - probe is best effort
            log.warning("pool_proxy_geo_failed", account_id=str(account_id), error=str(exc)[:150])

    if pool_email is not None:
        persona = build_persona(city, pool_email.domain or domain)
        persona.email_alias = pool_email.alias
    else:
        persona = build_persona(city, domain)

    with session_scope() as session:
        account = Account(
            id=account_id,
            batch_id=batch_id,
            email=persona.email_alias,
            email_alias=persona.email_alias,
            first_name=persona.first_name,
            last_name=persona.last_name,
            zip=persona.zip,
            city=persona.city,
            password_enc=box.encrypt(persona.password),
            state=AccountState.NEW.value,
            email_pool_id=pool_email.id if pool_email else None,
            proxy_pool_id=pool_proxy.id if pool_proxy else None,
        )
        session.add(account)
        session.flush()
        return account.id


def quarantine(account_id: uuid.UUID, code: str, evidence: dict | None = None) -> None:
    with session_scope() as session:
        account = session.get(Account, account_id)
        if account is None:
            # quarantine.account_id is a FK to accounts: inserting for a row that no longer
            # exists raises IntegrityError and masks the error we were called to record.
            log.warning("quarantine_skipped_account_missing", account_id=str(account_id), code=code)
            return
        session.add(Quarantine(account_id=account_id, code=code, evidence=evidence or {}))
        if account is not None:
            account.state = AccountState.QUARANTINED.value
            account.substate = code
            account.quarantine_reason = code
            account.last_error_code = code[:16]
    log.error("account_quarantined", account_id=str(account_id), code=code)


async def run_signup(account_id: uuid.UUID, deps: SignupDeps, *, raw_proxy: str | None = None) -> AccountState:
    settings = deps.settings
    lock = AccountLockManager(ttl_seconds=900)
    if not lock.acquire(account_id):
        log.warning("account_locked", account_id=str(account_id))
        return AccountState.NEW
    lock.start_heartbeat()
    # signup_duration_seconds was declared in obs/metrics.py but never observed, so /metrics
    # reported a permanent 0 for it. Measured from the moment this worker owns the account
    # (lock taken) to the final state, i.e. the real browser start -> ACTIVE wall time.
    started_monotonic = time.monotonic()
    run_id: uuid.UUID | None = None
    try:
        run_id = open_run(account_id, kind="signup")
        with bind_context(account_id=str(account_id), run_id=str(run_id)):
            account = load_account(account_id)
            if account is None:
                raise KeyError(account_id)
            persona = build_persona(account.city or settings.target.cities[0], settings.email.domains[0], zip_override=account.zip)
            persona.first_name = account.first_name
            persona.last_name = account.last_name
            persona.email_alias = account.email

            # Imported pools take precedence over the generated defaults.
            from core.mailbox_factory import provider_for_account
            from core.pool import commit_email, commit_proxy, proxy_raw, release_email

            email_provider = provider_for_account(account, settings, fallback=deps.email)
            pool_proxy_raw = None
            if account.proxy_pool_id:
                from db.models import ProxyPool

                with session_scope() as session:
                    proxy_row = session.get(ProxyPool, account.proxy_pool_id)
                    if proxy_row is not None:
                        pool_proxy_raw = proxy_raw(proxy_row)
            effective_proxy = pool_proxy_raw or raw_proxy

            store = CheckpointStore(run_id)
            ctx = StageContext(
                account_id=account_id,
                run_id=run_id,
                state=AccountState(account.state),
                data={"persona": persona, "raw_proxy": effective_proxy},
            )
            flow = SignupFlow(
                settings=settings,
                gpm=deps.gpm,
                registry=deps.registry,
                email_provider=email_provider,
                captcha_chain=deps.captcha,
                sms_provider=deps.sms,
                artifacts=deps.artifacts,
            )
            machine = StateMachine(flow.stages())
            final = await machine.run(ctx, store)

            # Pool bookkeeping: a created account consumes the email; the proxy is always
            # consumed once the browser has been opened on it (the IP is already exposed).
            if account.email_pool_id:
                if final in (AccountState.ACTIVE, AccountState.WARMING, AccountState.ONBOARDED):
                    commit_email(account.email_pool_id)
                else:
                    release_email(account.email_pool_id)
            if account.proxy_pool_id:
                commit_proxy(account.proxy_pool_id)

            close_run(run_id, RunState.DONE if final == AccountState.ACTIVE else RunState.FAILED,)
            signup_total.labels(result=final.value.lower()).inc()
            signup_duration_seconds.observe(time.monotonic() - started_monotonic)
            return final
    except YFError as exc:
        code = getattr(exc, "code", "error")
        quarantine(account_id, code, {"error": str(exc)[:500], "meta": exc.meta})
        if run_id:
            close_run(run_id, RunState.FAILED)
        signup_total.labels(result="failed").inc()
        return AccountState.QUARANTINED
    except Exception as exc:  # noqa: BLE001
        quarantine(account_id, "unhandled", {"error": f"{type(exc).__name__}: {exc}"[:500]})
        if run_id:
            close_run(run_id, RunState.FAILED)
        signup_total.labels(result="failed").inc()
        return AccountState.DEAD
    finally:
        lock.stop_heartbeat()
        lock.release(account_id)


async def resume_account(account_id: uuid.UUID, deps: SignupDeps, *, raw_proxy: str | None = None) -> AccountState:
    """Resume a crashed run: reopen the GPM profile, re-attach CDP, continue from checkpoint."""
    from adapters.browser import attach
    from adapters.gpm_ops import profile_name as _profile_name
    from db.models import Profile

    settings = deps.settings
    lock = AccountLockManager(ttl_seconds=900)
    if not lock.acquire(account_id):
        return AccountState.NEW
    lock.start_heartbeat()
    run_id: uuid.UUID | None = None
    browser = None
    try:
        account = load_account(account_id)
        if account is None:
            raise KeyError(account_id)
        # We hold the account lock, so any leftover RUNNING row belongs to a dead worker.
        with session_scope() as session:
            session.query(Run).filter(Run.account_id == account_id, Run.state == RunState.RUNNING.value).update(
                {"state": RunState.FAILED.value}
            )
        run_id = open_run(account_id, kind="resume")
        with bind_context(account_id=str(account_id), run_id=str(run_id)):
            persona = build_persona(account.city or settings.target.cities[0], settings.email.domains[0], zip_override=account.zip)
            persona.first_name = account.first_name
            persona.last_name = account.last_name
            persona.email_alias = account.email

            # Imported pools stay authoritative on resume too.
            from core.mailbox_factory import provider_for_account
            from core.pool import proxy_raw

            email_provider = provider_for_account(account, settings, fallback=deps.email)
            if account.proxy_pool_id:
                from db.models import ProxyPool

                with session_scope() as session:
                    proxy_row = session.get(ProxyPool, account.proxy_pool_id)
                    if proxy_row is not None:
                        raw_proxy = proxy_raw(proxy_row) or raw_proxy

            ctx = StageContext(account_id=account_id, run_id=run_id, state=AccountState(account.state), data={"persona": persona, "raw_proxy": raw_proxy})
            state = AccountState(account.state)

            # Any state past BROWSER_UP needs a live browser again.
            if state in {
                AccountState.BROWSER_UP,
                AccountState.PREWARMED,
                AccountState.FORM_FILLED,
                AccountState.CAPTCHA_SOLVED,
                AccountState.SUBMITTED,
                AccountState.ONBOARDED,
                AccountState.EMAIL_PENDING,
                AccountState.EMAIL_VERIFIED,
                AccountState.PHONE_PENDING,
                AccountState.PHONE_VERIFIED,
            }:
                with session_scope() as session:
                    profile_row = (
                        session.query(Profile).filter(Profile.id == account.profile_id).one_or_none()
                        if account.profile_id
                        else None
                    )
                    gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
                if gpm_profile_id:
                    started = _start_profile_safely(deps, gpm_profile_id)
                    browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
                    ctx.data["browser"] = browser
                    ctx.data["start_result"] = started
                    ctx.data["profile"] = type("P", (), {"id": gpm_profile_id})()
            else:
                gpm_profile_id = None

            if ctx.data.get("next") is None:
                # Re-derive the branch from the current page when possible.
                page = ctx.data.get("browser").page if ctx.data.get("browser") else None
                if page is not None:
                    try:
                        content = (await page.content()).lower()
                        if "extra-form" in content or "save & continue" in content:
                            ctx.data["next"] = "onboarding"
                    except Exception:  # noqa: BLE001
                        pass

            store = CheckpointStore(run_id)
            flow = SignupFlow(
                settings=settings,
                gpm=deps.gpm,
                registry=deps.registry,
                email_provider=email_provider,
                captcha_chain=deps.captcha,
                sms_provider=deps.sms,
                artifacts=deps.artifacts,
            )
            machine = StateMachine(flow.stages())
            final = await machine.run(ctx, store, start_from=state)

            # Pool bookkeeping mirrors run_signup(): resume must consume/release the same rows.
            if account.email_pool_id:
                from core.pool import commit_email, release_email

                if final in (AccountState.ACTIVE, AccountState.WARMING, AccountState.ONBOARDED):
                    commit_email(account.email_pool_id)
                else:
                    release_email(account.email_pool_id)
            if account.proxy_pool_id:
                from core.pool import commit_proxy

                commit_proxy(account.proxy_pool_id)

            close_run(run_id, RunState.DONE if final == AccountState.ACTIVE else RunState.FAILED)
            return final
    except YFError as exc:
        quarantine(account_id, getattr(exc, "code", "error"), {"error": str(exc)[:500], "meta": exc.meta})
        if run_id:
            close_run(run_id, RunState.FAILED)
        return AccountState.QUARANTINED
    except Exception as exc:  # noqa: BLE001
        quarantine(account_id, "unhandled", {"error": f"{type(exc).__name__}: {exc}"[:500]})
        if run_id:
            close_run(run_id, RunState.FAILED)
        return AccountState.DEAD
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        lock.stop_heartbeat()
        lock.release(account_id)


async def probe_account(account_id: uuid.UUID, deps: SignupDeps) -> dict:
    """Check whether the Yelp account exists by re-submitting its email on /signup.

    Login itself sits behind DataDome on this proxy, but the signup page answers
    "already registered" for existing emails, which is a reliable existence probe.
    """
    from adapters.browser import attach
    from core.crypto import SecretBox
    from db.models import Profile
    from human.mouse import human_click
    from human.typing import human_type
    from selector_registry.resolver import SelectorRegistry

    settings = deps.settings
    account = load_account(account_id)
    if account is None:
        return {"exists": False, "reason": "account_missing"}
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    # A missing profile only means the run died early; the account may still exist on Yelp.

    password = SecretBox().decrypt(account.password_enc) if account.password_enc else ""
    registry = deps.registry or SelectorRegistry.from_yaml()
    from adapters.proxysession import rotate_session

    probe_raw = rotate_session(
        settings.proxy.default_raw,
        f"probe-{account_id}-{int(time.time())}",
        sticky_minutes=settings.proxy.sticky_minutes,
    )
    temp = deps.gpm.create_profile(
        name=f"yf-probe-{str(account_id)[:8]}",
        raw_proxy=probe_raw,
        browser_version=settings.gpm.browser_version,
    )
    started = deps.gpm.start_profile(temp.id, window_size="1280,800", skip_proxy_check=True)
    browser = None
    try:
        browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
        page = browser.page
        await page.goto("https://www.yelp.com/signup?locale=en_US", wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(3000)
        for key, value in (
            ("signup.first_name", account.first_name),
            ("signup.last_name", account.last_name),
            ("signup.email", account.email),
            ("signup.password", password or "TempPass123!x"),
            ("signup.postal_code", account.zip),
        ):
            field = await registry.find(page, key, required=False, timeout_ms=6000)
            if field is not None:
                await human_type(field, value)
        submit = await registry.find(page, "signup.submit", required=False, timeout_ms=5000)
        if submit is None:
            return {"exists": None, "reason": "signup_form_missing", "email": account.email}
        await human_click(page, submit)
        await page.wait_for_timeout(9000)

        content = (await page.content()).lower()
        url = page.url
        # The signup page always contains "Already on Yelp? Log in", so a bare "already"
        # check is a false positive. Use the page state instead.
        if "welcome to yelp" in content or ("extra-form" in content and "signup-form" not in content):
            result = {"exists": True, "reason": "created_now", "email": account.email}
        elif "signup-form" in content and ("already registered" in content or "already have an account" in content):
            result = {"exists": True, "reason": "already_registered", "email": account.email}
        elif "signup-form" in content and "wrong" in content:
            result = {"exists": True, "reason": "wrong_password", "email": account.email}
        else:
            errors = await registry.find(page, "signup.inline_error", required=False, timeout_ms=2000)
            texts = []
            if errors is not None:
                try:
                    texts = await errors.all_inner_texts()
                except Exception:  # noqa: BLE001
                    texts = []
            result = {"exists": None, "reason": "inconclusive", "email": account.email, "url": url, "errors": texts[:3]}
        with session_scope() as session:
            row = session.get(Account, account_id)
            if row is not None:
                row.substate = f"probe_{result['reason']}"
        return result
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            deps.gpm.stop_profile(temp.id)
        except Exception:  # noqa: BLE001
            pass
        try:
            deps.gpm.delete_profile(temp.id, hard=True)
        except Exception:  # noqa: BLE001
            pass


async def verify_login(account_id: uuid.UUID, deps: SignupDeps, *, auto_login: bool = True) -> dict:
    """Prove the account exists by logging in with the stored credential.

    When the probe fails and ``auto_login`` is set, fall back to the full LoginFlow
    on the account's own profile (passwordless email link, spec v3.0 section 4).
    """
    probe = await _verify_login_probe(account_id, deps)
    if probe.get("ok") or not auto_login:
        return probe
    if probe.get("reason") in {"account_missing", "no_gpm_profile"}:
        return probe
    try:
        login = await login_account(account_id, deps)
    except Exception as exc:  # noqa: BLE001
        return {**probe, "auto_login": {"ok": False, "error": str(exc)[:150]}}
    return {
        "ok": login.get("ok"),
        "email": probe.get("email"),
        "reason": login.get("error_code") or login.get("status"),
        "auto_login": login,
    }


async def _verify_login_probe(account_id: uuid.UUID, deps: SignupDeps) -> dict:
    """Prove the account exists by logging in with the stored credential."""
    from adapters.browser import attach
    from core.crypto import SecretBox
    from db.models import Profile
    from human.mouse import human_click
    from human.typing import human_type

    settings = deps.settings
    account = load_account(account_id)
    if account is None:
        return {"ok": False, "reason": "account_missing"}
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        return {"ok": False, "reason": "no_gpm_profile", "email": account.email}

    password = SecretBox().decrypt(account.password_enc) if account.password_enc else ""
    from adapters.proxysession import rotate_session

    login_raw = rotate_session(
        settings.proxy.default_raw, f"login-{account_id}-{int(time.time())}", sticky_minutes=settings.proxy.sticky_minutes
    )
    temp = deps.gpm.create_profile(
        name=f"yf-login-{str(account_id)[:8]}",
        raw_proxy=login_raw,
        browser_version=settings.gpm.browser_version,
    )
    started = deps.gpm.start_profile(temp.id, window_size="1280,800", skip_proxy_check=True)
    browser = None
    try:
        browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
        page = browser.page
        await page.goto("https://www.yelp.com/login?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)
        html = ""
        try:
            html = (await page.content()).lower()
        except Exception:  # noqa: BLE001
            pass
        if "captcha-delivery" in html or "datadome" in html:
            return {"ok": None, "reason": "datadome_blocked", "email": account.email}

        # A live session redirects away from /login straight to the homepage.
        from adapters.browser import is_logged_in

        if await is_logged_in(page):
            with session_scope() as session:
                row = session.get(Account, account_id)
                if row is not None:
                    row.substate = "login_ok"
            return {"ok": True, "email": account.email, "url": page.url, "reason": "already_logged_in"}

        email_field = await deps.registry.find(page, "login.email", required=False, timeout_ms=6000)
        password_field = await deps.registry.find(page, "login.password", required=False, timeout_ms=4000)
        if email_field is None or password_field is None:
            return {"ok": False, "reason": "login_form_missing", "email": account.email, "url": page.url}
        await human_type(email_field, account.email)
        await human_type(password_field, password)
        submit = await deps.registry.find(page, "login.submit", required=False, timeout_ms=4000)
        if submit is None:
            return {"ok": False, "reason": "login_submit_missing", "email": account.email}
        await human_click(page, submit)
        await page.wait_for_timeout(7000)

        has_session = await is_logged_in(page)
        try:
            content = (await page.content()).lower()
        except Exception:  # noqa: BLE001
            content = ""
        wrong = "wrong email or password" in content or "incorrect" in content
        if has_session and not wrong:
            with session_scope() as session:
                row = session.get(Account, account_id)
                if row is not None:
                    row.substate = "login_ok"
            return {"ok": True, "email": account.email, "url": page.url, "state": account.state}
        with session_scope() as session:
            row = session.get(Account, account_id)
            if row is not None:
                row.substate = "login_failed"
        return {
            "ok": False,
            "reason": "wrong_credentials" if wrong else "no_session",
            "email": account.email,
            "url": page.url,
        }
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            deps.gpm.stop_profile(temp.id)
        except Exception:  # noqa: BLE001
            pass
        try:
            deps.gpm.delete_profile(temp.id, hard=True)
        except Exception:  # noqa: BLE001
            pass


class _FakemailoReader:
    """Mail-reader browser used only to read fakemailo (E-67).

    Mobile proxies cannot reach fakemailo, so the reader runs on its own GPM profile
    (``settings.login.mail_reader_profile_id``). It is started on demand, counts as a
    browser slot (max_concurrent profiles) and is stopped right after the link fetch.
    Note: the passwordless link is fetched from a different IP than the target profile
    - Yelp tolerated this in the 2026-11-08 run, but treat random session deaths as
    possibly caused by that mismatch.
    """

    def __init__(self, deps: SignupDeps, settings):
        self.deps = deps
        self.settings = settings
        self.browser = None
        self.profile_id: str | None = None
        self._slot = None

    async def page(self):
        if self.browser is not None:
            return self.browser.page
        profile_id = self.settings.login.mail_reader_profile_id
        if not profile_id:
            return None  # caller falls back to the target page
        # The reader profile is a real browser and counts against the 2-profile cap.
        from core.lock import acquire_slot, release_slot

        slot = acquire_slot(f"mailer-{uuid.uuid4().hex[:6]}", self.settings.post_review.max_concurrent, purpose="mailer")
        if slot is None:
            log.warning("mail_reader_slot_unavailable", max_concurrent=self.settings.post_review.max_concurrent)
            return None
        self._slot = slot
        started = self.deps.gpm.start_profile(profile_id, window_size="1280,800", skip_proxy_check=True)
        self.profile_id = profile_id
        from adapters.browser import attach

        self.browser = await attach(started.cdp_url, timeout_s=self.settings.gpm.connect_timeout_s)
        return self.browser.page

    async def close(self) -> None:
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:  # noqa: BLE001
                pass
            self.browser = None
        if self.profile_id:
            try:
                self.deps.gpm.stop_profile(self.profile_id)
            except Exception:  # noqa: BLE001
                pass
            self.profile_id = None
        if getattr(self, "_slot", None):
            from core.lock import release_slot

            release_slot(self._slot)
            self._slot = None


async def login_account(account_id: uuid.UUID, deps: SignupDeps, *, slot_held: bool = False) -> dict:
    """Full LoginFlow on the account's own GPM profile (spec v3.0 section 4).

    The session cookie lands in the profile, so warm/review runs keep it across
    browser restarts (T-10). Obeys the global browser-slot cap (never >2 profiles).
    """
    from adapters.browser import attach, is_logged_in
    from core.crypto import SecretBox
    from core.lock import acquire_slot, release_slot
    from db.models import Profile
    from flows.login_flow import LoginFlow

    settings = deps.settings
    own_slot = None
    if not slot_held:
        own_slot = acquire_slot(f"login-{uuid.uuid4().hex[:6]}", settings.post_review.max_concurrent, purpose="login")
        if own_slot is None:
            return {"ok": False, "status": "SLOTS_FULL", "error_code": "slots_full"}
    try:
        return await _login_account_body(account_id, deps, settings, attach, is_logged_in, SecretBox, Profile, LoginFlow)
    finally:
        if own_slot is not None:
            release_slot(own_slot)


async def _login_account_body(account_id, deps, settings, attach, is_logged_in, SecretBox, Profile, LoginFlow) -> dict:
    account = load_account(account_id)
    if account is None:
        return {"ok": False, "status": "FAILED", "error_code": "account_missing"}
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        return {"ok": False, "status": "FAILED", "error_code": "no_gpm_profile", "email": account.email}

    password = SecretBox().decrypt(account.password_enc) if account.password_enc else ""
    started = _start_profile_safely(deps, gpm_profile_id)
    browser = None
    reader = _FakemailoReader(deps, settings)
    try:
        browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
        # Session detection needs a real Yelp page (freshly started profiles open blank).
        try:
            await browser.page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
            await browser.page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001
            pass
        if await is_logged_in(browser.page):
            with session_scope() as session:
                row = session.get(Account, account_id)
                if row is not None:
                    row.substate = "login_ok"
            return {"ok": True, "status": "SUCCESS", "email": account.email, "reason": "already_logged_in"}

        mail_provider = None
        if settings.email.provider == "fakemailo":
            from adapters.email_fakemailo import FakemailoMailbox

            async def reader_page():
                page = await reader.page()
                return page if page is not None else browser.page

            mail_provider = FakemailoMailbox(
                url=settings.email.fakemailo_url,
                service=settings.email.fakemailo_service,
                page_factory=reader_page,
            )
        else:
            from core.mailbox_factory import provider_for_account

            mail_provider = provider_for_account(account, settings, fallback=deps.email)

        flow = LoginFlow(registry=deps.registry, settings=settings, email_provider=mail_provider)
        result = await flow.run(
            browser.page,
            email=account.email,
            password=password,
            user_id=account.yelp_user_id,
            alias=account.email_alias,
        )
        with session_scope() as session:
            row = session.get(Account, account_id)
            if row is not None:
                row.substate = "login_ok" if result.ok else f"login_{result.error_code or result.status.lower()}"
        if not result.ok and result.error_code == "login_link_timeout":
            from core.alerts import notify as alert

            alert("mail_link_timeout", account=account.email, detail={"source": "fakemailo", **result.detail})
        if result.ok:
            _clear_proxy_failure(account_id)
        return {"email": account.email, **result.to_json()}
    finally:
        await reader.close()
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            deps.gpm.stop_profile(gpm_profile_id)
        except Exception:  # noqa: BLE001
            pass


async def upload_avatar(account_id: uuid.UUID, deps: SignupDeps, *, avatar_path: str | None = None) -> dict:
    """Upload the stored avatar through /user_photos/add (works only with a live session)."""
    from pathlib import Path

    from adapters.browser import attach
    from db.models import Profile

    settings = deps.settings
    account = load_account(account_id)
    if account is None:
        return {"ok": False, "reason": "account_missing"}
    path = Path(avatar_path or account.avatar_path or "")
    if not path.exists():
        return {"ok": False, "reason": "avatar_missing"}
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        return {"ok": False, "reason": "no_gpm_profile"}

    started = _start_profile_safely(deps, gpm_profile_id)
    browser = None
    try:
        browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
        page = browser.page
        await page.goto("https://www.yelp.com/user_photos/add", wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(4000)
        files = page.locator("input[type='file']")
        if not await files.count():
            return {"ok": False, "reason": "upload_not_available", "url": page.url}
        await files.first.set_input_files(str(path.resolve()))
        await page.wait_for_timeout(8000)
        with session_scope() as session:
            row = session.get(Account, account_id)
            if row is not None:
                row.substate = "avatar_uploaded"
                row.avatar_path = str(path)
        return {"ok": True, "url": page.url, "avatar": str(path)}
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            deps.gpm.stop_profile(gpm_profile_id)
        except Exception:  # noqa: BLE001
            pass


async def run_profile_completion(account_id: uuid.UUID, deps: SignupDeps) -> dict:
    """Fill every optional profile field (about me, location, birthday) on an existing account."""
    from adapters.browser import attach
    from db.models import Profile
    from flows.identity import build_identity
    from flows.profile_settings import fill_birthday, fill_profile_details

    settings = deps.settings
    account = load_account(account_id)
    if account is None:
        raise KeyError(account_id)
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        raise RuntimeError("account has no GPM profile; run signup first")

    identity = build_identity(
        account_id=account.email or str(account_id),
        first_name=account.first_name or "User",
        last_name=account.last_name or "Yelp",
        city_state=account.city or "Austin, TX",
        zip_code=account.zip or "78701",
    )
    started = _start_profile_safely(deps, gpm_profile_id)
    browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
    result: dict = {}
    try:
        page = await browser.adopt_page()
        for step_name, step_coro in (
            ("details", fill_profile_details(page, deps.registry, identity)),
            ("birthday", fill_birthday(page, deps.registry, identity)),
        ):
            try:
                result.update(await step_coro or {})
            except Exception as exc:  # noqa: BLE001
                log.warning("profile_step_skipped", step=step_name, error=str(exc)[:180])
        if result:
            with session_scope() as session:
                row = session.get(Account, account_id)
                if row is not None:
                    row.substate = "profile_completed"
                    row.gender = identity.gender
                    row.birth_date = identity.birth_date.isoformat()
                    row.address_line = identity.address_line()
    finally:
        try:
            await browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            deps.gpm.stop_profile(gpm_profile_id)
        except Exception:  # noqa: BLE001
            pass
    return {"account": str(account_id), "filled": result}


async def run_warm(account_id: uuid.UUID, deps: SignupDeps, *, sessions: int = 1, max_seconds: int = 720) -> dict:
    """Warm an ACTIVE account: reopen the profile, run N human-like sessions."""
    from adapters.browser import attach
    from core.budget import DailyBudget, phase_for_day
    from db.models import Profile
    from flows.warmup import WarmingRunner

    settings = deps.settings
    account = load_account(account_id)
    if account is None:
        raise KeyError(account_id)
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        raise RuntimeError("account has no GPM profile; run signup first")

    started = _start_profile_safely(deps, gpm_profile_id)
    browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
    runner = WarmingRunner(gpm=deps.gpm, registry=deps.registry, settings=settings)
    from core.scheduler import daily_plan_day

    day = daily_plan_day(account_id)
    phase = phase_for_day(day)
    plan = DailyBudget.for_phase(phase)
    results = []
    try:
        for index in range(sessions):
            empty = __import__("human.timing", fromlist=["empty_session"]).empty_session()
            outcome = await runner.run_session(
                _WarmCtx(account_id, browser, phase=phase, proxy_ip=getattr(account, "proxy_ip", None)),
                budget=plan,
                empty=empty,
                max_seconds=max_seconds,
            )
            results.append(outcome)
            persist_account_state(account_id, AccountState.WARMING, substate=account.substate)
    finally:
        try:
            await browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            deps.gpm.stop_profile(gpm_profile_id)
        except Exception:  # noqa: BLE001
            pass
    return {"account": str(account_id), "sessions": results, "budget": plan.to_json()}


async def run_post_review_warm(account_id: uuid.UUID, deps: SignupDeps, *, max_seconds: int | None = None) -> dict:
    """Post-review maintenance session (spec v3.0 section 5): login if needed, then
    walk the P0->P4 ladder once, capped at 60 minutes, no review actions."""
    from adapters.browser import attach, is_logged_in
    from core.post_review import sessions_today
    from db.models import Profile
    from flows.post_review_warm import PostReviewWarmRunner

    settings = deps.settings
    account = load_account(account_id)
    if account is None:
        return {"ok": False, "error_code": "account_missing"}
    if not account.reviews_done:
        # E-80: the mode is reserved for accounts that finished the review phase.
        return {"ok": False, "error_code": "not_reviews_done", "email": account.email}
    from db.models import Metro

    with session_scope() as session:
        metro = session.get(Metro, account.metro_id) if account.metro_id else None
        tz_name = metro.timezone if metro else "UTC"
    if sessions_today(account_id, tz_name=tz_name) >= settings.post_review.sessions_per_day:
        return {"ok": True, "status": "SKIPPED_TODAY", "email": account.email}

    from core.lock import AccountLockManager, acquire_slot, release_slot

    # HARD RULE: never more than max_concurrent (2) open profiles, no matter how the
    # session was triggered (scheduler, CLI --account, manual run).
    slot = acquire_slot(f"warm-{uuid.uuid4().hex[:8]}", settings.post_review.max_concurrent, purpose="warm")
    if slot is None:
        return {"ok": True, "status": "SLOTS_FULL", "email": account.email, "max_concurrent": settings.post_review.max_concurrent}

    locks = AccountLockManager(worker_id=f"warm-{uuid.uuid4().hex[:8]}")
    if not locks.acquire(account_id):
        release_slot(slot)
        return {"ok": True, "status": "LOCKED", "email": account.email}
    try:
        return await _run_post_review_session(account_id, deps, account, max_seconds=max_seconds)
    finally:
        locks.release(account_id)
        release_slot(slot)


def _start_profile_safely(deps: SignupDeps, profile_id: str, *, window_size: str | None = None):
    """Start a GPM profile, recovering from a leftover browser (ProfileInUse, B5).

    A crashed worker can leave the profile open after its slot TTL expires; on the next
    start GPM raises ProfileInUse. Stop the orphan and retry once - a reconcile step that
    needs no extra GPM endpoint.
    """
    import time as _time

    effective_window_size = window_size if window_size else window_size_for_profile(profile_id)
    try:
        return deps.gpm.start_profile(profile_id, window_size=effective_window_size, skip_proxy_check=True)
    except Exception as exc:  # noqa: BLE001
        if "ProfileInUse" not in str(exc):
            raise
        log.warning("orphan_profile_reconcile", profile_id=profile_id)
        try:
            deps.gpm.stop_profile(profile_id)
        except Exception:  # noqa: BLE001
            pass
        _time.sleep(2)
        return deps.gpm.start_profile(profile_id, window_size=effective_window_size, skip_proxy_check=True)


def _note_proxy_failure(account_id, *, severity_threshold: int = 2) -> int:
    """Count consecutive tunnel failures; escalate the alert at the threshold (D)."""
    from core.flags import get_flag, set_flag

    key = f"proxy_fail:{account_id}"
    flag = get_flag(key, {})
    count = int(flag.get("count", 0)) + 1
    set_flag(key, {"count": count, "last": datetime.now(timezone.utc).isoformat()})
    if count >= severity_threshold:
        from core.alerts import notify as alert

        alert("proxy_dead_repeated", severity="critical", detail={"account": str(account_id), "count": count})
    return count


def _clear_proxy_failure(account_id) -> None:
    from core.flags import set_flag

    set_flag(f"proxy_fail:{account_id}", {"count": 0})


async def _run_post_review_session(account_id: uuid.UUID, deps: SignupDeps, account, *, max_seconds: int | None = None) -> dict:
    from adapters.browser import attach, is_logged_in
    from db.models import Account, Profile
    from db.session import session_scope

    settings = deps.settings

    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        return {"ok": False, "error_code": "no_gpm_profile", "email": account.email}

    # "sau khi đăng nhập thì nuôi" - restore the session first (T-10 skips if alive).
    started = _start_profile_safely(deps, gpm_profile_id)
    browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
    try:
        await browser.page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
        await browser.page.wait_for_timeout(3000)
    except Exception:  # noqa: BLE001
        pass
    logged_in = await is_logged_in(browser.page)
    try:
        await browser.close()
    except Exception:  # noqa: BLE001
        pass
    if not logged_in:
        login = await login_account(account_id, deps, slot_held=True)
        if not login.get("ok"):
            return {"ok": False, "error_code": login.get("error_code", "login_failed"), "login": login}

    started = _start_profile_safely(deps, gpm_profile_id)
    browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
    runner = PostReviewWarmRunner(registry=deps.registry, settings=settings)

    try:
        outcome = await runner.run_session(
            browser.page,
            account_id=account_id,
            proxy_ip=getattr(account, "proxy_ip", None),
            max_seconds=max_seconds,
            city=account.city,
            user_id=account.yelp_user_id,
            # measured flag, not account age: Betty is a 5-day seed but never had an avatar
            fill_profile=not bool(account.profile_complete),
            account_tag=account.email,
        )
        if "profile_filled" in outcome.get("actions", []):
            with session_scope() as session:
                row = session.get(Account, account_id)
                if row is not None:
                    row.profile_complete = True
        _clear_proxy_failure(account_id)
    finally:
        try:
            await browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            deps.gpm.stop_profile(gpm_profile_id)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "status": "COMPLETED", "email": account.email, **outcome}


async def run_due_reviews(deps: SignupDeps, *, limit: int = 5) -> dict:
    """Post every due review assignment (same-metro rule enforced by the planner)."""
    from adapters.browser import attach, is_logged_in
    from core.alerts import notify as alert
    from core.assignments import due_assignments, mark_failed, mark_published
    from core.lock import AccountLockManager
    from core.volume import effective_multiplier
    from db.models import Account, Profile, ReviewAttempt
    from flows.review_phase import ReviewPoster

    if effective_multiplier() <= 0:
        return {"skipped": "volume_zero"}

    settings = deps.settings
    locks = AccountLockManager(worker_id=f"review-{uuid.uuid4().hex[:8]}")
    poster = ReviewPoster(registry=deps.registry, settings=settings)
    results: list[dict] = []

    for item in due_assignments(limit=limit):
        account_id = uuid.UUID(item["account_id"])
        assignment_id = uuid.UUID(item["assignment_id"])
        if not locks.acquire(account_id):
            results.append({"assignment": str(assignment_id), "skipped": "locked"})
            continue
        from core.lock import acquire_slot, release_slot

        slot = acquire_slot(f"review-{uuid.uuid4().hex[:6]}", settings.post_review.max_concurrent, purpose="review")
        if slot is None:
            locks.release(account_id)
            results.append({"assignment": str(assignment_id), "skipped": "slots_full"})
            continue
        browser = None
        gpm_profile_id = None
        try:
            account = load_account(account_id)
            if account is None:
                mark_failed(assignment_id, "account_missing")
                continue
            # Lifecycle lock: city just changed (<48h), failed the gate, or blacklisted.
            from core.lifecycle import review_block_reason

            blocked = review_block_reason(account)
            if blocked:
                results.append({"assignment": str(assignment_id), "skipped": blocked})
                continue
            with session_scope() as session:
                profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
                gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
            if not gpm_profile_id:
                mark_failed(assignment_id, "no_gpm_profile")
                continue

            started = _start_profile_safely(deps, gpm_profile_id)
            browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
            page = browser.page
            try:
                await page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(2500)
            except Exception:  # noqa: BLE001
                pass
            if not await is_logged_in(page):
                await browser.close()
                browser = None
                login = await login_account(account_id, deps)
                if not login.get("ok"):
                    mark_failed(assignment_id, f"login:{login.get('error_code') or login.get('status')}")
                    alert("review_login_failed", account=account.email, detail=login)
                    continue
                started = _start_profile_safely(deps, gpm_profile_id)
                browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
                page = browser.page

            existing_texts = []
            with session_scope() as session:
                rows = (
                    session.query(ReviewAttempt.text)
                    .filter(ReviewAttempt.business_id == item["yelp_biz_id"], ReviewAttempt.text.is_not(None))
                    .all()
                )
                existing_texts = [text for (text,) in rows if text]

            outcome = await poster.post(
                page,
                business_name=item["business_name"],
                yelp_biz_id=item["yelp_biz_id"],
                category=item.get("category") or "other",
                facts=item.get("facts") or {},
                existing_texts=existing_texts,
            )
            if not outcome.get("posted"):
                mark_failed(assignment_id, outcome.get("reason") or "not_posted")
                alert("review_not_posted", account=account.email, detail={"assignment": str(assignment_id), **outcome})
                results.append({"assignment": str(assignment_id), "posted": False, "reason": outcome.get("reason")})
                continue

            with session_scope() as session:
                attempt = ReviewAttempt(
                    account_id=account_id,
                    business_id=item["yelp_biz_id"],
                    rating=int(outcome["rating"]),
                    words=len(str(outcome["text"]).split()),
                    text=outcome["text"],
                    photo=bool(outcome.get("photo")),
                    status="submitted",
                )
                session.add(attempt)
                session.flush()
                attempt_id = attempt.id
            mark_published(assignment_id, review_attempt_id=attempt_id)
            results.append({"assignment": str(assignment_id), "posted": True, "rating": outcome["rating"]})
        except Exception as exc:  # noqa: BLE001
            mark_failed(assignment_id, str(exc)[:200])
            alert("review_crashed", detail={"assignment": str(assignment_id), "error": str(exc)[:300]})
            results.append({"assignment": str(assignment_id), "error": str(exc)[:200]})
        finally:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001
                    pass
            if gpm_profile_id:
                try:
                    deps.gpm.stop_profile(gpm_profile_id)
                except Exception:  # noqa: BLE001
                    pass
            release_slot(slot)
            locks.release(account_id)

    return {"count": len(results), "results": results}


async def check_published_reviews(deps: SignupDeps, *, hours: int = 72, limit: int = 10) -> dict:
    """72h re-check: still Recommended or filtered? -> assignments.filtered_at + warranty replacement."""
    from adapters.browser import attach, is_logged_in
    from core.alerts import notify as alert
    from core.assignments import due_for_check, mark_filtered, plan_replacement
    from core.lock import AccountLockManager
    from db.models import Profile, ReviewAttempt
    from flows.review_phase import ReviewPoster

    settings = deps.settings
    locks = AccountLockManager(worker_id=f"check-{uuid.uuid4().hex[:8]}")
    poster = ReviewPoster(registry=deps.registry, settings=settings)
    results: list[dict] = []

    for item in due_for_check(hours=hours, limit=limit):
        account_id = uuid.UUID(item["account_id"])
        assignment_id = uuid.UUID(item["assignment_id"])
        if not locks.acquire(account_id):
            continue
        from core.lock import acquire_slot, release_slot

        slot = acquire_slot(f"check-{uuid.uuid4().hex[:6]}", settings.post_review.max_concurrent, purpose="check")
        if slot is None:
            locks.release(account_id)
            continue
        browser = None
        gpm_profile_id = None
        try:
            account = load_account(account_id)
            if account is None:
                continue
            with session_scope() as session:
                profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
                gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
                snippet_row = (
                    session.query(ReviewAttempt.text)
                    .filter(ReviewAttempt.account_id == account_id, ReviewAttempt.business_id == item["yelp_biz_id"])
                    .order_by(ReviewAttempt.ts.desc())
                    .first()
                )
            if not gpm_profile_id or snippet_row is None or not snippet_row[0]:
                mark_filtered(assignment_id, filtered=False)
                continue
            snippet = str(snippet_row[0])

            started = _start_profile_safely(deps, gpm_profile_id)
            browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
            page = browser.page
            await page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2000)
            if not await is_logged_in(page):
                results.append({"assignment": str(assignment_id), "skipped": "not_logged_in"})
                continue

            filtered = await poster.is_filtered(page, yelp_biz_id=item["yelp_biz_id"], snippet=snippet)
            mark_filtered(assignment_id, filtered=filtered)
            replacement = None
            if filtered:
                replacement = plan_replacement(uuid.UUID(item["client_id"]), account_id)
                alert(
                    "review_filtered",
                    account=account.email,
                    detail={
                        "assignment": str(assignment_id),
                        "business": item["business_name"],
                        "warranty_replacement": replacement,
                    },
                )
            results.append({"assignment": str(assignment_id), "filtered": filtered, "replacement": replacement})
        except Exception as exc:  # noqa: BLE001
            results.append({"assignment": str(assignment_id), "error": str(exc)[:200]})
        finally:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001
                    pass
            if gpm_profile_id:
                try:
                    deps.gpm.stop_profile(gpm_profile_id)
                except Exception:  # noqa: BLE001
                    pass
            release_slot(slot)
            locks.release(account_id)

    return {"count": len(results), "results": results}


async def run_post_review_due(deps: SignupDeps, *, limit: int = 20, max_seconds: int | None = None) -> dict:
    """Run one post-review session for every flagged account that owes one today.

    Sequential on purpose: one account per proxy at a time (spec 5.6). Respects
    the local 07:00-22:30 window.
    """
    from core.post_review import due_accounts, within_window

    settings = deps.settings
    if not settings.post_review.enabled:
        return {"skipped": "disabled"}
    if not within_window(start=settings.post_review.window_start, end=settings.post_review.window_end):
        # host-local window is only a coarse guard; the metro window below is authoritative
        pass

    from core.lock import acquire_slot, release_slot
    from core.post_review import within_account_window
    from db.models import Account, Metro

    results = []
    for account_id in due_accounts(limit):
        try:
            with session_scope() as session:
                account = session.get(Account, account_id)
                metro = session.get(Metro, account.metro_id) if account and account.metro_id else None
                tz = metro.timezone if metro else "America/New_York"
            if not within_account_window(tz, start=settings.post_review.window_start, end=settings.post_review.window_end):
                results.append({"account": str(account_id), "skipped": "outside_metro_window", "timezone": tz})
                continue
            outcome = await run_post_review_warm(account_id, deps, max_seconds=max_seconds)
            results.append(outcome)
            if outcome.get("status") == "SLOTS_FULL":
                break  # hard cap reached: stop the sweep, never open a third profile
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "ERR_TUNNEL" in msg or "ERR_PROXY" in msg:
                with session_scope() as session:
                    row = session.get(Account, account_id)
                    if row is not None:
                        row.state = "COOLDOWN"
                        row.substate = "proxy_dead"
                count = _note_proxy_failure(account_id)
                results.append({"account": str(account_id), "ok": False, "error_code": "proxy_dead", "consecutive": count})
            else:
                results.append({"account": str(account_id), "ok": False, "error": msg[:150]})
    return {"count": len(results), "results": results}


async def probe_stale_sessions(deps: SignupDeps, *, stale_days: int = 3, limit: int = 10) -> dict:
    """Light session probe (no login submit): detect captcha / under-review early."""
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from db.models import Account, WarmingSession
    from db.session import session_scope

    cutoff = _dt.now(timezone.utc) - _td(days=stale_days)
    recent = _dt.now(timezone.utc) - _td(hours=12)
    with session_scope() as session:
        rows = (
            session.query(Account.id)
            .filter(
                Account.state.in_(["READY", "ACTIVE"]),
                (Account.last_probe_at.is_(None)) | (Account.last_probe_at < cutoff),
            )
            .order_by(Account.last_probe_at.asc().nullsfirst())
            .limit(limit * 2)
            .all()
        )
        ids = []
        for (account_id,) in rows:
            # no point probing right after a warm session (same run, same browser already verified)
            warmed_recently = (
                session.query(WarmingSession.id)
                .filter(
                    WarmingSession.account_id == account_id,
                    WarmingSession.mode == "post_review",
                    WarmingSession.started_at >= recent,
                )
                .first()
            )
            if warmed_recently:
                continue
            ids.append(account_id)
            if len(ids) >= limit:
                break

    results = []
    for account_id in ids:
        results.append(await probe_session(account_id, deps))
    return {"count": len(results), "results": results}


async def probe_session(account_id: uuid.UUID, deps: SignupDeps) -> dict:
    """Open the account's own profile, verify the session/challenge state, close."""
    from datetime import datetime as _dt

    from adapters.browser import attach, is_logged_in
    from core.alerts import notify as alert
    from core.lock import acquire_slot, release_slot
    from db.models import Account, Profile

    settings = deps.settings
    slot = acquire_slot(f"probe-{uuid.uuid4().hex[:6]}", settings.post_review.max_concurrent, purpose="probe")
    if slot is None:
        return {"account": str(account_id), "skipped": "slots_full"}
    account = load_account(account_id)
    if account is None:
        release_slot(slot)
        return {"account": str(account_id), "ok": False, "reason": "account_missing"}
    with session_scope() as session:
        profile_row = session.query(Profile).filter(Profile.id == account.profile_id).one_or_none() if account.profile_id else None
        gpm_profile_id = profile_row.gpm_profile_id if profile_row else None
    if not gpm_profile_id:
        release_slot(slot)
        return {"account": str(account_id), "ok": False, "reason": "no_gpm_profile"}

    started = _start_profile_safely(deps, gpm_profile_id)
    browser = None
    try:
        browser = await attach(started.cdp_url, timeout_s=settings.gpm.connect_timeout_s)
        page = browser.page
        try:
            await page.goto("https://www.yelp.com/?locale=en_US", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2500)
        except Exception:  # noqa: BLE001
            pass
        logged = await is_logged_in(page)
        try:
            content = (await page.content()).lower()
        except Exception:  # noqa: BLE001
            content = ""
        challenge = [m for m in ("captcha-delivery", "verify your identity", "account under review", "are you a robot", "hcaptcha") if m in content]

        with session_scope() as session:
            row = session.get(Account, account_id)
            if row is not None:
                row.last_probe_at = _dt.now(timezone.utc)
                if challenge:
                    row.state = "NEEDS_MANUAL"
                    row.substate = "probe_challenge"
        if challenge:
            alert("account_challenge", account=account.email, detail={"markers": challenge})
        return {
            "account": str(account_id),
            "ok": logged and not challenge,
            "logged_in": logged,
            "challenge": challenge,
            "url": page.url,
        }
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "ERR_TUNNEL" in msg or "ERR_PROXY" in msg:
            # Proxy died: park the account, never auto-rebind another proxy (2026-11-09).
            with session_scope() as session:
                row = session.get(Account, account_id)
                if row is not None:
                    row.state = "COOLDOWN"
                    row.substate = "proxy_dead"
            count = _note_proxy_failure(account_id)
            alert("proxy_dead", account=account.email, detail={"error": msg[:300], "consecutive": count})
        else:
            alert("probe_crashed", account=account.email, detail={"error": msg[:300]})
        return {"account": str(account_id), "ok": False, "error": msg[:200]}
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            deps.gpm.stop_profile(gpm_profile_id)
        except Exception:  # noqa: BLE001
            pass
        release_slot(slot)


class _WarmCtx:
    def __init__(self, account_id: uuid.UUID, browser, *, phase: str = "P1", proxy_ip: str | None = None, plan_id=None):
        self.account_id = account_id
        self.data = {
            "browser": browser,
            "phase": phase,
            "proxy_ip": proxy_ip,
            "plan_id": plan_id,
            "review_enabled": True,
            "entry_path": __import__("random").choices(
                ["search", "direct", "category", "referral"], weights=[6, 2, 1, 1], k=1
            )[0],
        }


async def run_batch(account_ids: list[uuid.UUID], deps: SignupDeps, *, concurrency: int = 1, proxy: str | None = None) -> dict:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: dict[str, str] = {}

    async def one(account_id: uuid.UUID) -> None:
        async with semaphore:
            final = await run_signup(account_id, deps, raw_proxy=proxy)
            results[str(account_id)] = final.value

    await asyncio.gather(*(one(aid) for aid in account_ids))
    return results
