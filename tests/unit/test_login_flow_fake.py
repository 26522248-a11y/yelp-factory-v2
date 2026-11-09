"""LoginFlow against fakes: the real-world 2026-11-08 scenarios (T-2, T-5, T-6)."""

from __future__ import annotations

import pytest

from adapters.email import MailMessage, VerificationMail
from flows.login_flow import LoginFlow
from selector_registry.resolver import SelectorRegistry, SelectorRule
from tests.fakes import FakeMouse, FakePage

pytestmark = pytest.mark.asyncio

REGISTRY = SelectorRegistry(
    {
        "login.email": [SelectorRule("css", "form#ajax-login input#email", 1)],
        "login.password": [SelectorRule("css", "form#ajax-login input#password", 1)],
        "login.submit": [SelectorRule("css", "form#ajax-login button[type='submit']", 1)],
        "login.resend_link": [SelectorRule("text", "Send another one", 1)],
        "passwordless.continue_btn": [SelectorRule("css", "button:has-text('Continue')", 1)],
    }
)

LOGIN_LINK = "https://www.yelp.com/login/passwordless/redirect/MLA123abc?ytl_=tok"


class HookedMouse(FakeMouse):
    """human_click presses through page.mouse; emulate the submit SPA response there."""

    async def click(self, x: float, y: float) -> None:
        await super().click(x, y)
        page = self.page
        if "passwordless" not in page.url and "user_details" not in page.url and "login" in page.url:
            page.scripted_text = page.on_submit_text


class ScriptedPage(FakePage):
    """FakePage whose body text/html changes with the URL, like the real SPA."""

    def __init__(self):
        super().__init__(url="https://www.yelp.com/login")
        self.scripted_text = "Log in to Yelp"
        self.on_submit_text = ""
        self.mouse = HookedMouse(self)

    async def goto(self, url: str, **kwargs):
        await super().goto(url, **kwargs)
        if "passwordless/redirect" in url:
            self.scripted_text = "Log In to Yelp Logging in as Betty M."
            self.html = '<a href="/user_details?userid=42">account</a>'
            self.add("button:has-text('Continue')", visible=True)
        elif "user_details" in url:
            self.scripted_text = "Betty M. New York, NY Edit profile Add photo"
        else:
            self.scripted_text = "Log in to Yelp"

    async def evaluate(self, script: str, arg=None):
        if "innerText" in script:
            return self.scripted_text
        return await super().evaluate(script, arg)


class FakeMail:
    def __init__(self, link: str = LOGIN_LINK):
        self.link = link
        self.calls: list[dict] = []

    async def wait_for_verification(self, alias, *, timeout_s: int = 120, since=None):
        self.calls.append({"alias": alias, "timeout_s": timeout_s, "since": since})
        return VerificationMail(
            message=MailMessage(id="m1", subject="Your Yelp login link is here!", sender="no-reply@yelp.com", recipients=[alias], body=""),
            link=self.link,
        )

    async def probe(self, alias: str) -> bool:
        return True


def make_flow(settings, mail):
    settings.login.submit_poll_s = 2
    settings.login.max_password_attempts = 2
    settings.login.max_resend = 1
    settings.login.link_timeout_s = 5
    return LoginFlow(registry=REGISTRY, settings=settings, email_provider=mail)


def setup_form(page: ScriptedPage):
    page.add("form#ajax-login input#email", visible=True)
    page.add("form#ajax-login input#password", visible=True)
    page.add("form#ajax-login button[type='submit']", visible=True)


async def test_email_link_challenge_full_success(settings):
    page = ScriptedPage()
    setup_form(page)
    page.on_submit_text = "We need to confirm it's really you. We've sent an email with a login link to a@b.com."
    mail = FakeMail()
    flow = make_flow(settings, mail)

    result = await flow.run(page, email="a@b.com", password="pw", user_id="42")
    assert result.ok and result.status == "SUCCESS"
    assert mail.calls and mail.calls[0]["since"] is not None
    assert any("passwordless/redirect" in url for url in page.gotos)
    assert any(event[0] == "mouse_click" for event in page.events)  # Continue pressed (T-6)


async def test_E66_continue_missing_is_never_success(settings):
    page = ScriptedPage()
    setup_form(page)
    page.on_submit_text = "We've sent an email with a login link to a@b.com."
    mail = FakeMail()
    flow = make_flow(settings, mail)

    original_goto = page.goto

    async def goto_no_confirm(url, **kwargs):
        await original_goto(url, **kwargs)
        if "passwordless/redirect" in url:
            page.scripted_text = "something else entirely"

    page.goto = goto_no_confirm

    result = await flow.run(page, email="a@b.com", password="pw", user_id="42")
    assert not result.ok
    assert result.status == "NEEDS_REVIEW"
    assert result.error_code == "login_confirm_missing"


async def test_bad_credentials_fails_fast_without_mail(settings):
    page = ScriptedPage()
    setup_form(page)
    page.on_submit_text = "The email or password you entered doesn't look right."
    mail = FakeMail()
    flow = make_flow(settings, mail)

    result = await flow.run(page, email="a@b.com", password="pw")
    assert result.status == "FAILED"
    assert result.error_code == "login_bad_credentials"
    assert not mail.calls  # no link fetch after a hard credential failure


async def test_toast_retries_then_transient(settings):
    page = ScriptedPage()
    setup_form(page)
    page.on_submit_text = "We're unable to log you in right now. Please try again later."
    mail = FakeMail()
    flow = make_flow(settings, mail)

    result = await flow.run(page, email="a@b.com", password="pw")
    assert result.status == "NEEDS_REVIEW"
    assert result.error_code == "login_transient"


async def test_already_logged_in_skips_submit(settings):
    page = ScriptedPage()
    setup_form(page)
    page.html = '<a href="/user_details?userid=42">account</a>'
    page.scripted_text = "Betty M. Edit profile"
    mail = FakeMail()
    flow = make_flow(settings, mail)

    result = await flow.run(page, email="a@b.com", password="pw", user_id="42")
    assert result.ok and result.stage == "precheck"
    assert not mail.calls
    assert not any(event[0] == "type" for event in page.events)  # T-10: never resubmit
