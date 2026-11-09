"""Fakemailo reader: link extraction from the srcdoc iframe (T-5) and stale-mail guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adapters.base import NoVerificationMail
from adapters.email_fakemailo import FakemailoInbox, FakemailoMailbox

pytestmark = pytest.mark.asyncio

LINK = "https://www.yelp.com/login/passwordless/redirect/MLA987xyz?ytl_=tok&utm_medium=email"
OLD_LINK = "https://www.yelp.com/login/passwordless/redirect/MLA000old?ytl_=old"


class FakeFakemailoPage:
    def __init__(self, links: list[str], text: str):
        self.links = links
        self.text = text
        self.selected: str | None = None
        self.clicks: list[str] = []
        self.gotos: list[str] = []
        self.fills: list[str] = []

    async def goto(self, url: str, **kwargs):
        self.gotos.append(url)

    async def wait_for_timeout(self, ms: int):
        return None

    async def select_option(self, selector: str, label: str | None = None, **kwargs):
        self.selected = label

    async def evaluate(self, script: str, arg=None):
        return {"links": self.links, "text": self.text}

    def locator(self, selector: str):
        page = self

        class _Loc:
            async def fill(self, value):
                page.fills.append(value)

            async def click(self, **kwargs):
                page.clicks.append(selector)

        return _Loc()


def reader_text(link: str, received: str) -> str:
    return f"fakemailo Inbox no-reply@yelp.com Your Yelp login link is here! Read Email From: no-reply@yelp.com {received} Log in {link}"


def test_inbox_extracts_passwordless_link():
    inbox = FakemailoInbox(links=[LINK], text="whatever")
    assert inbox.login_link() == LINK
    assert inbox.looks_like_login_mail() is False  # sender/subject missing from text


def test_inbox_extracts_link_embedded_in_srcdoc_text():
    inbox = FakemailoInbox(links=[], text=reader_text(LINK, "2026-11-08T16:55:24Z"))
    assert inbox.login_link() == LINK
    assert inbox.looks_like_login_mail() is True
    assert inbox.received_at() == datetime(2026, 11, 8, 16, 55, 24, tzinfo=timezone.utc)


def test_inbox_verify_link_fallback():
    verify = "https://www.yelp.com/signup/confirm?token=abc"
    inbox = FakemailoInbox(links=[verify], text="")
    assert inbox.login_link() is None
    assert inbox.verify_link() == verify


async def test_mailbox_returns_fresh_link():
    page = FakeFakemailoPage(links=[LINK], text=reader_text(LINK, "2026-11-08T16:55:24Z"))
    mailbox = FakemailoMailbox(page_factory=lambda: _async(page), poll_interval_s=0.01)

    mail = await mailbox.wait_for_verification("a@outlook.com", timeout_s=1, since=None)
    assert mail.link == LINK
    assert page.selected == "Yelp"
    assert page.fills == ["a@outlook.com"]


async def test_E64_stale_link_is_not_returned():
    page = FakeFakemailoPage(links=[OLD_LINK], text=reader_text(OLD_LINK, "2026-11-01T10:00:00Z"))
    mailbox = FakemailoMailbox(page_factory=lambda: _async(page), poll_interval_s=0.01)
    since = datetime.now(timezone.utc) - timedelta(minutes=5)

    with pytest.raises(NoVerificationMail):
        await mailbox.wait_for_verification("a@outlook.com", timeout_s=1, since=since)


async def test_stale_then_fresh_link_is_accepted():
    fresh_at = (datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_at = "2026-11-01T10:00:00Z"

    class EvolvingPage(FakeFakemailoPage):
        async def evaluate(self, script: str, arg=None):
            if len(self.clicks) >= 1 or self.turn:
                return {"links": [LINK], "text": reader_text(LINK, fresh_at)}
            self.turn = True
            return {"links": [OLD_LINK], "text": reader_text(OLD_LINK, old_at)}

    page = EvolvingPage(links=[], text="")
    page.turn = False
    mailbox = FakemailoMailbox(page_factory=lambda: _async(page), poll_interval_s=0.01)
    since = datetime.now(timezone.utc) - timedelta(minutes=5)

    mail = await mailbox.wait_for_verification("a@outlook.com", timeout_s=2, since=since)
    assert mail.link == LINK


async def _async(value):
    return value
