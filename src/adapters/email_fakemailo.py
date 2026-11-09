"""Fakemailo partner-authorized-emails reader (real-world 2026-11-08: T-5, T-7, T-8).

Microsoft suspended the outlook.com mailboxes, so the login link is read through
https://fakemailo.com/partner-authorized-emails: fill the address, pick the service,
press "Get email", then take the ``passwordless/redirect`` link out of the reader
(the message body renders inside an ``about:srcdoc`` iframe).

The page used here must NOT be the target account's browser page when its proxy is a
mobile proxy (E-67): those tunnels cannot reach fakemailo. Callers pass a page from a
dedicated mail-reader profile and open the returned link in the *target* profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from adapters.base import EmailError, NoVerificationMail
from adapters.email import MailMessage, VerificationMail
from obs.log import get_logger

log = get_logger("email_fakemailo")

PASSWORDLESS_LINK_RE = re.compile(
    r"https?://(?:www\.)?yelp\.[a-z.]+/login/passwordless/redirect/[A-Za-z0-9]+[^\s\"'<>]*",
    re.IGNORECASE,
)
VERIFY_LINK_RE = re.compile(
    r"https?://(?:www\.)?yelp\.[a-z.]+/(?:signup[/?][^\s\"'<>]*|confirm[^\s\"'<>]*|verify[^\s\"'<>]*)",
    re.IGNORECASE,
)
LOGIN_MAIL_SENDER = "no-reply@yelp.com"
LOGIN_MAIL_SUBJECT = "Your Yelp login link is here"
READER_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")

# Reads every anchor href plus the visible body text of the document AND of every
# same-origin (srcdoc) iframe in one shot.
_EXTRACT_JS = """() => {
    const out = {links: [], text: (document.body ? document.body.innerText : '')};
    for (const a of document.querySelectorAll('a[href]')) out.links.push(a.href);
    for (const frame of document.querySelectorAll('iframe')) {
        try {
            const doc = frame.contentDocument;
            if (!doc) continue;
            for (const a of doc.querySelectorAll('a[href]')) out.links.push(a.href);
            if (doc.body) out.text += ' ' + doc.body.innerText;
        } catch (e) { /* cross-origin frame */ }
    }
    return out;
}"""


@dataclass(slots=True)
class FakemailoInbox:
    links: list[str]
    text: str

    def login_link(self) -> str | None:
        for link in self.links:
            if PASSWORDLESS_LINK_RE.search(link):
                return link
        match = PASSWORDLESS_LINK_RE.search(self.text)
        return match.group(0) if match else None

    def verify_link(self) -> str | None:
        for link in self.links:
            if VERIFY_LINK_RE.search(link):
                return link
        return None

    def received_at(self) -> datetime | None:
        match = READER_DATE_RE.search(self.text)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def looks_like_login_mail(self) -> bool:
        return LOGIN_MAIL_SENDER in self.text and LOGIN_MAIL_SUBJECT.lower() in self.text.lower()


class FakemailoMailbox:
    """Implements the ``EmailProvider`` protocol on top of the fakemailo web reader."""

    def __init__(
        self,
        *,
        url: str = "https://fakemailo.com/partner-authorized-emails",
        service: str = "Yelp",
        page_factory: Callable[[], Awaitable[Any]] | None = None,
        poll_interval_s: float = 5.0,
    ):
        self.url = url
        self.service = service
        self._page_factory = page_factory
        self.poll_interval_s = poll_interval_s

    # ------------------------------------------------------------------ protocol

    async def wait_for_verification(self, alias: str, *, timeout_s: int = 120, since: datetime | None = None) -> VerificationMail:
        page = await self._get_page()
        inbox = await self._request_and_poll(page, alias, timeout_s=timeout_s, since=since)
        link = inbox.login_link() or inbox.verify_link()
        if not link:
            raise NoVerificationMail(f"no link in fakemailo reader for {alias} after {timeout_s}s")
        received = inbox.received_at()
        message = MailMessage(
            id=f"fakemailo-{alias}",
            subject=LOGIN_MAIL_SUBJECT if inbox.login_link() else "fakemailo",
            sender=LOGIN_MAIL_SENDER,
            recipients=[alias],
            body=inbox.text[:2000],
            received_at=received,
        )
        log.info("fakemailo_link_found", alias=alias, since=since.isoformat() if since else None)
        return VerificationMail(message=message, link=link)

    async def probe(self, alias: str) -> bool:
        try:
            page = await self._get_page()
        except Exception:  # noqa: BLE001
            return False
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=45_000)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("fakemailo_probe_failed", error=str(exc)[:150])
            return False

    # ------------------------------------------------------------------ internals

    async def _get_page(self):
        if self._page_factory is None:
            raise EmailError("fakemailo needs a page_factory (mail-reader profile)", code="mail_channel")
        return await self._page_factory()

    async def _request_and_poll(self, page, alias: str, *, timeout_s: int, since: datetime | None) -> "FakemailoInbox":
        await page.goto(self.url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1500)

        email_input = page.locator("#email")
        await email_input.fill(alias)
        try:
            await page.select_option("#service", label=self.service)
        except Exception:  # noqa: BLE001
            log.warning("fakemailo_service_select_failed", service=self.service)
        get_button = page.locator("#btn-get-code")
        await get_button.click()

        waited = 0.0
        requested_again = False
        stale_inbox: FakemailoInbox | None = None
        inbox = FakemailoInbox(links=[], text="")
        while waited <= timeout_s:
            await page.wait_for_timeout(self.poll_interval_s * 1000)
            waited += self.poll_interval_s
            inbox = await self.extract(page)
            link = inbox.login_link() or inbox.verify_link()
            if link:
                # E-64: the box keeps old login mails around; ignore anything older than
                # the submit timestamp unless the reader date is unavailable.
                received = inbox.received_at()
                if since is not None and received is not None and received < since:
                    stale_inbox = inbox
                    if not requested_again:
                        requested_again = True
                        log.info("fakemailo_stale_mail", alias=alias, received=received.isoformat())
                    continue
                return inbox
            # E-65 rescue: the reader sometimes needs a refresh click after the mail lands.
            if waited > timeout_s / 2 and not requested_again:
                requested_again = True
                try:
                    await get_button.click()
                except Exception:  # noqa: BLE001
                    pass
        if stale_inbox is not None:
            # Only stale mail ever showed up: do not hand back a consumed/expired link.
            cleaned = PASSWORDLESS_LINK_RE.sub("[stale-link]", stale_inbox.text)
            return FakemailoInbox(links=[], text=cleaned)
        return inbox

    @staticmethod
    async def extract(page) -> "FakemailoInbox":
        try:
            data = await page.evaluate(_EXTRACT_JS)
            return FakemailoInbox(links=list(data.get("links", [])), text=str(data.get("text", "")))
        except Exception as exc:  # noqa: BLE001
            log.warning("fakemailo_extract_failed", error=str(exc)[:150])
            return FakemailoInbox(links=[], text="")
