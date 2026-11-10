"""AES-GCM encryption for account secrets (section 14)."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import get_settings


class SecretBox:
    def __init__(self, key_b64: str | None = None):
        raw = (key_b64 if key_b64 is not None else get_settings().master_key) or ""
        raw = raw.strip()
        # A blank key is "not configured", not a passphrase: treating "   " as a key would
        # encrypt/decrypt with a garbage key and turn a config mistake into a corrupt blob.
        if not raw:
            raise RuntimeError("YF_MASTER_KEY is not configured; refusing to store secrets in clear")
        # A key that is not urlsafe-base64 is a configuration mistake too. The old
        # "plain 32-byte passphrase" fallback silently derived a garbage key, so a single typo
        # both encrypted with junk and made healthy blobs look corrupt (AN probe 11/11: a
        # malformed key quarantined a good token blob, and re-encrypted a legacy plaintext
        # token with the junk key before deleting it). Fail loudly instead: callers already
        # treat "box cannot be built" as a config error and leave stored blobs in place.
        try:
            self._key = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        except Exception as exc:  # noqa: BLE001 - normalise every decode failure
            raise ValueError("YF_MASTER_KEY must be urlsafe-base64 of 16/24/32 bytes") from exc
        if len(self._key) not in (16, 24, 32):
            raise ValueError("master key must decode to 16/24/32 bytes")
        self._aead = AESGCM(self._key)

    def encrypt(self, plaintext: str, aad: bytes | None = None) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aead.encrypt(nonce, plaintext.encode("utf-8"), aad)

    def decrypt(self, blob: bytes, aad: bytes | None = None) -> str:
        return self._aead.decrypt(blob[:12], blob[12:], aad).decode("utf-8")


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")
