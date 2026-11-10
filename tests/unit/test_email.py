from __future__ import annotations

import pytest

from pathlib import Path

from adapters.email import FakeMailbox, MailMessage, VERIFY_LINK_RE

pytestmark = pytest.mark.asyncio

LINK = "https://www.yelp.com/signup/verify?token=abc123&uid=42"


def message(to: str = "alias@fviainboxes.com", body: str = f"Click {LINK}", folder: str = "inbox") -> MailMessage:
    return MailMessage(
        id="m1",
        subject="Verify your email for Yelp",
        sender="Yelp <no-reply@yelp.com>",
        recipients=[to],
        body=body,
        folder=folder,
    )


def test_link_is_extracted():
    assert message().verification_link() == LINK


def test_link_regex_handles_locale_host():
    text = "https://www.yelp.ca/signup/confirm?token=zzz"
    match = VERIFY_LINK_RE.search(text)
    assert match and match.group(0) == text


def test_expired_markers():
    assert message(body="This link has expired").looks_expired()
    assert not message().looks_expired()


async def test_wait_returns_first_matching_mail():
    box = FakeMailbox()
    box.deliver(to="alias@fviainboxes.com", subject="Verify your email", link=LINK)
    mail = await box.wait_for_verification("alias@fviainboxes.com", timeout_s=1)
    assert mail.link == LINK


async def test_mail_for_other_alias_is_ignored():
    box = FakeMailbox()
    box.deliver(to="other@fviainboxes.com", subject="Verify", link=LINK)
    from adapters.base import NoVerificationMail

    with pytest.raises(NoVerificationMail):
        await box.wait_for_verification("alias@fviainboxes.com", timeout_s=0.2)


async def test_junk_folder_mail_is_found():
    """E-07: mail that lands in Junk must still be picked up."""
    box = FakeMailbox()
    box.deliver(to="alias@fviainboxes.com", subject="Verify", link=LINK, folder="junkemail")
    mail = await box.wait_for_verification("alias@fviainboxes.com", timeout_s=1)
    assert mail.message.folder == "junkemail"


# ------------------------------------------------------------------ refresh token at rest


def _token_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "email_refresh_token.bin"


def test_refresh_token_is_stored_encrypted(tmp_path):
    """The persisted Graph token must be a SecretBox blob, not readable plaintext."""
    from adapters.email import REFRESH_TOKEN_AAD, _load_refresh_token
    from core.crypto import SecretBox

    path = _token_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(SecretBox().encrypt("rt-secret-value", aad=REFRESH_TOKEN_AAD))

    assert _load_refresh_token(path) == "rt-secret-value"
    assert b"rt-secret-value" not in path.read_bytes()


def test_persist_callback_writes_secretbox_blob(settings, tmp_path):
    """GraphMailbox.on_token_refresh must persist the rotated token encrypted."""
    from adapters.email import REFRESH_TOKEN_AAD, GraphMailbox, _load_refresh_token, build_provider
    from core.crypto import SecretBox

    settings.email.provider = "ms_graph"
    settings.email.graph_client_id = "client-id"
    settings.email.graph_refresh_token = "cfg-token"
    settings.artifacts_dir = str(tmp_path / "artifacts")

    provider = build_provider(settings)
    assert isinstance(provider, GraphMailbox)
    provider._on_refresh("rotated-token")

    path = _token_path(tmp_path)
    blob = path.read_bytes()
    assert b"rotated-token" not in blob
    assert SecretBox().decrypt(blob, aad=REFRESH_TOKEN_AAD) == "rotated-token"
    assert _load_refresh_token(path) == "rotated-token"


def test_corrupt_token_file_falls_back_to_config(settings, tmp_path):
    """A corrupted blob (or rotated master key) must not raise: fall back to config."""
    from adapters.email import GraphMailbox, build_provider

    settings.email.provider = "ms_graph"
    settings.email.graph_client_id = "client-id"
    settings.email.graph_refresh_token = "cfg-token"
    settings.artifacts_dir = str(tmp_path / "artifacts")

    path = _token_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not-a-secretbox-blob")

    provider = build_provider(settings)
    assert isinstance(provider, GraphMailbox)
    assert provider.refresh_token == "cfg-token"


def test_unreadable_blob_is_quarantined_and_reported(settings, tmp_path, capsys):
    """A blob encrypted with another master key must not be reused silently (AN finding 2)."""
    from adapters.email import GraphMailbox, build_provider

    settings.email.provider = "ms_graph"
    settings.email.graph_client_id = "client-id"
    settings.email.graph_refresh_token = "cfg-token"
    settings.artifacts_dir = str(tmp_path / "artifacts")

    path = _token_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"blob-encrypted-with-the-old-master-key")

    provider = build_provider(settings)
    assert isinstance(provider, GraphMailbox)
    assert provider.refresh_token == "cfg-token"
    assert not path.exists(), "the unreadable blob must be moved out of the way"
    quarantined = list(path.parent.glob("email_refresh_token.corrupt-*.bin"))
    assert len(quarantined) == 1
    out = capsys.readouterr().out
    assert "refresh_token_unreadable" in out


def test_legacy_plaintext_txt_is_deleted_when_blob_exists(tmp_path):
    """A stale plaintext .txt must never survive next to a good blob (AN finding 3)."""
    from adapters.email import REFRESH_TOKEN_AAD, _load_refresh_token
    from core.crypto import SecretBox

    path = _token_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(SecretBox().encrypt("blob-token", aad=REFRESH_TOKEN_AAD))
    legacy = path.with_suffix(".txt")
    legacy.write_text("legacy-token", encoding="utf-8")

    assert _load_refresh_token(path) == "blob-token"
    assert not legacy.exists(), "plaintext legacy token must be removed from disk"
    kept = path.with_suffix(".legacy.bin")
    assert kept.exists()
    assert SecretBox().decrypt(kept.read_bytes(), aad=REFRESH_TOKEN_AAD) == "legacy-token"


def test_legacy_plaintext_txt_is_migrated_when_no_blob(tmp_path):
    from adapters.email import REFRESH_TOKEN_AAD, _load_refresh_token
    from core.crypto import SecretBox

    path = _token_path(tmp_path)
    path.parent.mkdir(parents=True)
    legacy = path.with_suffix(".txt")
    legacy.write_text("legacy-token", encoding="utf-8")

    assert _load_refresh_token(path) == "legacy-token"
    assert not legacy.exists()
    assert SecretBox().decrypt(path.read_bytes(), aad=REFRESH_TOKEN_AAD) == "legacy-token"


def test_token_path_ignores_the_current_working_directory(settings, tmp_path, monkeypatch):
    """A relative artifacts_dir must resolve against the repo, not the cwd (AN finding 3)."""
    from adapters.email import ROOT, _token_file

    settings.artifacts_dir = "artifacts"
    monkeypatch.chdir(tmp_path)
    expected = ROOT / "data" / "email_refresh_token.bin"
    assert _token_file(settings) == expected
    assert _token_file(settings).is_absolute()
