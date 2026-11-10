"""Mailbox adapters: Microsoft Graph (primary), IMAP XOAUTH2, and a fake for tests.

The verification mail is matched on ``to:`` alias + Yelp sender, links are opened in the
existing tab (E-43) and tokens are single use (E-44).
"""

from __future__ import annotations

import asyncio
import base64
import html as html_mod
import imaplib
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx

from adapters.base import EmailError, NoVerificationMail
from core.crypto import SecretBox
from obs.log import get_logger

log = get_logger("email")

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# AAD binds the encrypted blob to this purpose: a blob lifted from another SecretBox
# column cannot be replayed as a refresh token.
REFRESH_TOKEN_AAD = b"email_refresh_token"

# Repo root: a relative artifacts_dir must resolve against the project, not the cwd.
ROOT = Path(__file__).resolve().parents[2]


def _token_file(settings) -> Path:
    """Absolute path of the token blob: a relative artifacts_dir must not depend on the cwd."""
    base = Path(settings.artifacts_dir)
    if not base.is_absolute():
        base = ROOT / base
    return base.parent / "data" / "email_refresh_token.bin"


def _restrict_to_owner(path: Path) -> None:
    """Best effort: keep the token blob readable by the current user only.

    ``chmod`` is a no-op for ACLs on Windows (measured: mode stays 0o666 and BUILTIN\\Users
    keeps read access), so the ACL is tightened explicitly there.
    """
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME") or ""
            if user:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
        else:
            path.chmod(0o600)
    except Exception:  # noqa: BLE001 - hardening must never be fatal
        log.warning("refresh_token_permissions_not_restricted", path=str(path))


def _consume_legacy_token(path: Path, *, have_blob: bool) -> str:
    """Encrypt and then delete a legacy plaintext ``email_refresh_token.txt``.

    The plaintext file is removed even when a valid blob exists - a credential must never
    stay readable on disk. When a good blob is already present the legacy value is kept
    aside encrypted instead of overwriting the newer token.

    An unusable ``YF_MASTER_KEY`` is reported as its own error and leaves the plaintext file
    in place: that is a configuration mistake (worker/CI started without the env var), not a
    corrupt file, and deleting the only readable copy would make it unrecoverable.
    """
    legacy = path.with_suffix(".txt")
    if not legacy.exists():
        return ""
    try:
        raw = legacy.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001 - never let a bad token file break provider setup
        log.error("refresh_token_legacy_unreadable")
        return ""
    if not raw:
        legacy.unlink(missing_ok=True)
        return ""
    try:
        box = SecretBox()
    except Exception:  # noqa: BLE001 - YF_MASTER_KEY missing, blank or malformed
        log.error(
            "refresh_token_legacy_key_missing",
            reason="YF_MASTER_KEY missing, blank or malformed",
            action="kept the plaintext .txt on disk; delete it by hand before handing the machine over",
        )
        return ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        target = path.with_suffix(".legacy.bin") if have_blob else path
        target.write_bytes(box.encrypt(raw, aad=REFRESH_TOKEN_AAD))
        _restrict_to_owner(target)
        log.warning("refresh_token_legacy_plaintext_migrated", target=target.name)
        legacy.unlink(missing_ok=True)
        return "" if have_blob else raw
    except Exception:  # noqa: BLE001 - never let a bad token file break provider setup
        log.error("refresh_token_legacy_migration_failed")
        return ""


def _load_refresh_token(path: Path) -> str:
    """Return the persisted Graph refresh token, or "" when there is none.

    The token is a credential, so it is stored AES-GCM encrypted with YF_MASTER_KEY.
    An absent file means "no token" (normal: the caller uses ``graph_refresh_token``).

    Two failures must stay distinguishable (AN probe, 11/11):

    * the box cannot be built at all - ``YF_MASTER_KEY`` is missing, blank or malformed
      (detached worktree, CI, worker started without the env var). The blob on disk is
      probably fine, so it is left exactly where it is; quarantining it here would destroy
      the only good copy because of a configuration mistake;
    * the box builds but ``decrypt`` fails - the master key was rotated or the file is
      corrupt. That is NOT normal, and silently reusing the stale configured token only
      surfaces much later as ``NoVerificationMail``, so report it at ERROR, quarantine the
      unreadable blob, and then fall back.
    """
    token = ""
    if path.exists():
        box = None
        try:
            box = SecretBox()
        except Exception:  # noqa: BLE001 - key missing/blank/malformed: keep the blob
            log.error(
                "refresh_token_key_missing",
                reason="YF_MASTER_KEY missing, blank or malformed",
                action="blob left in place; falling back to config graph_refresh_token",
            )
        if box is not None:
            try:
                token = box.decrypt(path.read_bytes(), aad=REFRESH_TOKEN_AAD).strip()
            except Exception:  # noqa: BLE001 - report the failure, never let it break setup
                log.error(
                    "refresh_token_unreadable",
                    reason="bad_master_key_or_corrupt_blob",
                    action="quarantined blob, falling back to config graph_refresh_token",
                )
                try:
                    path.replace(path.with_suffix(f".corrupt-{int(time.time())}.bin"))
                except Exception:  # noqa: BLE001
                    log.warning("refresh_token_quarantine_failed")
                token = ""
    # Always sweep a legacy plaintext .txt, even when the blob is good. ``have_blob`` is the
    # file, not the decrypted value: an empty token must never let the .txt overwrite a blob.
    legacy_token = _consume_legacy_token(path, have_blob=path.exists())
    return token or legacy_token


VERIFY_LINK_RE = re.compile(
    r"https?://(?:www\.)?yelp\.[a-z.]+/(?:signup[/?][^\s\"'<>]*|confirm[^\s\"'<>]*|verify[^\s\"'<>]*)",
    re.IGNORECASE,
)
EXPIRED_MARKERS = ("expired", "invalid", "no longer valid", "already been used")


@dataclass(slots=True)
class MailMessage:
    id: str
    subject: str
    sender: str
    recipients: list[str]
    body: str
    received_at: datetime | None = None
    folder: str = "inbox"

    def verification_link(self) -> str | None:
        match = VERIFY_LINK_RE.search(self.body) or VERIFY_LINK_RE.search(self.subject)
        return match.group(0) if match else None

    def looks_expired(self) -> bool:
        text = (self.subject + " " + self.body).lower()
        return any(marker in text for marker in EXPIRED_MARKERS)


@dataclass(slots=True)
class VerificationMail:
    message: MailMessage
    link: str


class EmailProvider(Protocol):
    async def wait_for_verification(self, alias: str, *, timeout_s: int, since: datetime | None = None) -> VerificationMail: ...

    async def probe(self, alias: str) -> bool: ...


# ---------------------------------------------------------------------------------------
# Microsoft Graph
# ---------------------------------------------------------------------------------------


class GraphMailbox:
    """Reads a consumer Outlook mailbox through Graph using an OAuth refresh token."""

    def __init__(
        self,
        client_id: str,
        refresh_token: str,
        *,
        tenant: str = "consumers",
        timeout: float = 20.0,
        on_token_refresh: Callable[[str], None] | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.tenant = tenant
        self.timeout = timeout
        self._on_refresh = on_token_refresh
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": "https://graph.microsoft.com/.default offline_access",
        }
        response = await self._client.post(TOKEN_URL.format(tenant=self.tenant), data=data)
        if response.status_code >= 400:
            raise EmailError(
                f"graph token refresh failed: {response.status_code} {response.text[:200]}",
                code="email_auth",
            )
        payload = response.json()
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + float(payload.get("expires_in", 3600))
        if new_token := payload.get("refresh_token"):
            # Microsoft rotates refresh tokens: keep the newest one.
            self.refresh_token = new_token
            if self._on_refresh:
                self._on_refresh(new_token)
        return self._access_token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._token()
        response = await self._client.get(
            f"{GRAPH}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"},
        )
        if response.status_code == 401:
            self._access_token = None
            token = await self._token()
            response = await self._client.get(
                f"{GRAPH}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
        if response.status_code >= 400:
            raise EmailError(f"graph {path} -> {response.status_code}: {response.text[:300]}")
        return response.json()

    async def list_messages(self, alias: str, *, folder: str = "inbox", top: int = 25) -> list[MailMessage]:
        base = "/me/messages" if folder == "inbox" else f"/me/mailFolders('{folder}')/messages"
        data = await self._get(
            base,
            {
                "$top": top,
                "$select": "id,subject,from,toRecipients,receivedDateTime,body",
                # $orderby is not allowed together with $search on Graph.
                "$search": f'"to:{alias}"',
            },
        )
        messages = []
        for item in data.get("value", []):
            body = (item.get("body") or {}).get("content") or ""
            if (content_type := (item.get("body") or {}).get("contentType")) == "html":
                body = html_mod.unescape(re.sub(r"<[^>]+>", " ", body))
            messages.append(
                MailMessage(
                    id=item.get("id", ""),
                    subject=item.get("subject") or "",
                    sender=((item.get("from") or {}).get("emailAddress") or {}).get("address", ""),
                    recipients=[
                        (r.get("emailAddress") or {}).get("address", "") for r in item.get("toRecipients", [])
                    ],
                    body=body,
                    received_at=_parse_dt(item.get("receivedDateTime")),
                    folder=folder,
                )
            )
        return messages

    async def wait_for_verification(
        self, alias: str, *, timeout_s: int = 180, since: datetime | None = None
    ) -> VerificationMail:
        deadline = time.monotonic() + timeout_s
        seen: set[str] = set()
        while time.monotonic() < deadline:
            # E-07: Yelp mail regularly lands in Junk.
            for folder in ("inbox", "junkemail"):
                try:
                    messages = await self.list_messages(alias, folder=folder)
                except EmailError as exc:
                    log.warning("mailbox_folder_error", folder=folder, error=str(exc)[:200])
                    continue
                for message in messages:
                    if message.id in seen:
                        continue
                    if since and message.received_at and message.received_at < since:
                        continue
                    link = message.verification_link()
                    if link:
                        return VerificationMail(message=message, link=link)
                    seen.add(message.id)
            await asyncio.sleep(5)
        raise NoVerificationMail(f"no verification mail for {alias} within {timeout_s}s")

    async def probe(self, alias: str, *, wait_s: int = 90) -> bool:
        """Send a probe mail from the mailbox itself to prove the alias is routable."""
        try:
            token = await self._token()
            payload = {
                "message": {
                    "subject": f"YF probe {alias}",
                    "body": {"contentType": "Text", "content": "probe"},
                    "toRecipients": [{"emailAddress": {"address": alias}}],
                },
                "saveToSentItems": False,
            }
            response = await self._client.post(
                f"{GRAPH}/me/sendMail", json=payload, headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code >= 400:
                raise EmailError(f"sendMail -> {response.status_code}: {response.text[:200]}", code="mail_send")
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                for message in await self.list_messages(alias):
                    if alias.lower() in " ".join(message.recipients).lower():
                        return True
                await asyncio.sleep(6)
            return False
        except EmailError:
            return False


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------
# IMAP XOAUTH2 fallback
# ---------------------------------------------------------------------------------------


class ImapMailbox:
    def __init__(self, host: str, user: str, client_id: str, refresh_token: str, *, tenant: str = "consumers"):
        self.host = host
        self.user = user
        self.client_id = client_id
        self.refresh_token = refresh_token
        self.tenant = tenant

    def _xoauth2(self) -> bytes:
        import httpx as _httpx

        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
        }
        response = _httpx.post(TOKEN_URL.format(tenant=self.tenant), data=data, timeout=20)
        response.raise_for_status()
        token = response.json()["access_token"]
        auth_string = f"user={self.user}\x01auth=Bearer {token}\x01\x01"
        return base64.b64encode(auth_string.encode()).decode().encode()

    def _fetch(self, folder: str) -> list[MailMessage]:
        conn = imaplib.IMAP4_SSL(self.host)
        try:
            conn.authenticate("XOAUTH2", lambda _: self._xoauth2())
            conn.select(folder)
            status, data = conn.search(None, "ALL")
            ids = data[0].split()[-25:] if status == "OK" else []
            messages: list[MailMessage] = []
            for msg_id in ids:
                status, payload = conn.fetch(msg_id, "(RFC822)")
                if status != "OK" or not payload:
                    continue
                import email as email_lib

                parsed = email_lib.message_from_bytes(payload[0][1])
                body = ""
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == "text/plain":
                            body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                else:
                    body = parsed.get_payload(decode=True).decode(parsed.get_content_charset() or "utf-8", "ignore")
                messages.append(
                    MailMessage(
                        id=msg_id.decode(),
                        subject=parsed.get("Subject", ""),
                        sender=parsed.get("From", ""),
                        recipients=[r.strip() for r in (parsed.get("To") or "").split(",")],
                        body=body,
                        folder=folder,
                    )
                )
            return messages
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass

    async def wait_for_verification(
        self, alias: str, *, timeout_s: int = 180, since: datetime | None = None
    ) -> VerificationMail:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for folder in ("INBOX", "Junk"):
                try:
                    messages = await asyncio.to_thread(self._fetch, folder)
                except Exception as exc:  # noqa: BLE001
                    log.warning("imap_fetch_failed", folder=folder, error=str(exc)[:200])
                    continue
                for message in messages:
                    if alias.lower() not in " ".join(message.recipients).lower():
                        continue
                    link = message.verification_link()
                    if link:
                        return VerificationMail(message=message, link=link)
            await asyncio.sleep(5)
        raise NoVerificationMail(f"no verification mail for {alias} within {timeout_s}s")

    async def probe(self, alias: str) -> bool:
        return True


# ---------------------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------------------


@dataclass
class FakeMailbox:
    messages: list[MailMessage] = field(default_factory=list)
    delay_s: float = 0.0
    sent: list[dict[str, Any]] = field(default_factory=list)

    def deliver(self, *, to: str, subject: str, link: str, folder: str = "inbox", delay_s: float = 0.0):
        body = f"Verify your Yelp account: {link}"
        self.messages.append(
            MailMessage(
                id=f"m{len(self.messages) + 1}",
                subject=subject,
                sender="Yelp <no-reply@yelp.com>",
                recipients=[to],
                body=body,
                received_at=datetime.now(timezone.utc),
                folder=folder,
            )
        )

    async def wait_for_verification(
        self, alias: str, *, timeout_s: int = 180, since: datetime | None = None
    ) -> VerificationMail:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for message in self.messages:
                if alias.lower() in " ".join(message.recipients).lower() and (link := message.verification_link()):
                    return VerificationMail(message=message, link=link)
            await asyncio.sleep(0.05)
        raise NoVerificationMail(f"no verification mail for {alias}")

    async def probe(self, alias: str) -> bool:
        self.sent.append({"to": alias})
        return True


def build_provider(settings) -> EmailProvider:
    cfg = settings.email
    if cfg.provider == "fake":
        return FakeMailbox()
    if cfg.provider == "fakemailo":
        from adapters.email_fakemailo import FakemailoMailbox

        return FakemailoMailbox(url=cfg.fakemailo_url, service=cfg.fakemailo_service)
    if cfg.provider == "imap":
        return ImapMailbox(
            cfg.imap_host, settings.email.domains[0], cfg.graph_client_id, cfg.graph_refresh_token, tenant=cfg.graph_tenant
        )
    # Microsoft rotates the refresh token on every exchange; keep the newest one on disk so
    # a crashed worker does not invalidate the mailbox for the next run. It is a credential,
    # so it is written AES-GCM encrypted (SecretBox) - never in clear text.
    token_file = _token_file(settings)
    # Read the blob BEFORE validating the config: while YF_MASTER_KEY is being rotated the
    # configured token is the dead one and the blob is the live one (AN probe b1, 11/11).
    token_blob = _load_refresh_token(token_file)
    if not cfg.graph_client_id or not (cfg.graph_refresh_token or token_blob):
        raise EmailError("graph credentials missing", code="email_config")
    refresh_token = token_blob or cfg.graph_refresh_token

    def persist(new_token: str) -> None:
        try:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_bytes(SecretBox().encrypt(new_token, aad=REFRESH_TOKEN_AAD))
            _restrict_to_owner(token_file)
        except Exception:  # noqa: BLE001 - a failed write must not kill the run
            log.warning("refresh_token_persist_failed")

    return GraphMailbox(
        cfg.graph_client_id,
        refresh_token,
        tenant=cfg.graph_tenant,
        on_token_refresh=persist,
    )
