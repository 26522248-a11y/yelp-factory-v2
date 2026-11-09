"""E-66: the passwordless page requires an explicit Continue click (real-world T-6).

Opening the login link is not enough - without the Continue press Yelp never sets
the session cookie, so the flow must never report success at that point.
"""

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

LINK = "https://www.yelp.com/login/passwordless/redirect/MLAe66?ytl_=t"
CHALLENGE = "We need to confirm it's really you. We've sent an email with a login link to a@b.com."


class ConfirmlessPage(FakePage):
    """Lands on the passwordless URL but shows no 'Logging in as' heading."""

    def __init__(self):
        super().__init__(url="https://www.yelp.com/login")
        self.scripted_text = "Log in to Yelp"
        self.mouse = _ChallengeMouse(self)

    async def goto(self, url: str, **kwargs):
        await super().goto(url, **kwargs)
        if "login" in url:
            self.scripted_text = "Log in to Yelp"
        else:
            self.scripted_text = "expired link page"

    async def evaluate(self, script: str, arg=None):
        if "innerText" in script:
            return self.scripted_text
        return await super().evaluate(script, arg)


class _ChallengeMouse(FakeMouse):
    async def click(self, x: float, y: float) -> None:
        await super().click(x, y)
        if "passwordless" not in self.page.url and "login" in self.page.url:
            self.page.scripted_text = CHALLENGE


class FakeMail:
    async def wait_for_verification(self, alias, *, timeout_s: int = 120, since=None):
        return VerificationMail(
            message=MailMessage(id="m", subject="Your Yelp login link is here!", sender="no-reply@yelp.com", recipients=[alias], body=""),
            link=LINK,
        )

    async def probe(self, alias: str) -> bool:
        return True


async def test_E66_missing_continue_never_reports_success(settings):
    settings.login.submit_poll_s = 2
    settings.login.max_password_attempts = 1
    settings.login.max_resend = 0
    settings.login.link_timeout_s = 2

    page = ConfirmlessPage()
    page.add("form#ajax-login input#email", visible=True)
    page.add("form#ajax-login input#password", visible=True)
    page.add("form#ajax-login button[type='submit']", visible=True)

    flow = LoginFlow(registry=REGISTRY, settings=settings, email_provider=FakeMail())
    result = await flow.run(page, email="a@b.com", password="pw", user_id="42")

    assert not result.ok
    assert result.status == "NEEDS_REVIEW"
    assert result.error_code == "login_confirm_missing"
