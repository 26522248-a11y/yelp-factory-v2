"""SecretBox key handling: only a real urlsafe-base64 key may build a box."""

from __future__ import annotations

import base64

import pytest

from core.crypto import SecretBox, generate_master_key


def test_generated_key_round_trips():
    box = SecretBox(key_b64=generate_master_key())
    assert box.decrypt(box.encrypt("secret", aad=b"purpose"), aad=b"purpose") == "secret"


def test_unpadded_urlsafe_key_is_accepted():
    raw = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    box = SecretBox(key_b64=raw)
    assert box.decrypt(box.encrypt("v")) == "v"


@pytest.mark.parametrize(
    "bad_key",
    ["", "   ", "###not-base64###", "dev-passphrase"],
    ids=["empty", "blank", "malformed", "passphrase"],
)
def test_unusable_key_refuses_to_build_a_box(bad_key):
    """A config mistake must fail loudly instead of deriving a junk key.

    The removed passphrase fallback silently encrypted with a garbage key, which also made
    healthy stored blobs look corrupt (quarantined) - see AN probe 11/11.
    """
    with pytest.raises((RuntimeError, ValueError)):
        SecretBox(key_b64=bad_key)


def test_wrong_length_key_is_rejected():
    with pytest.raises(ValueError):
        SecretBox(key_b64=base64.urlsafe_b64encode(b"short-key").decode())


def test_16_and_24_byte_keys_are_accepted():
    for size in (16, 24, 32):
        box = SecretBox(key_b64=base64.urlsafe_b64encode(b"k" * size).decode())
        assert box.decrypt(box.encrypt("v")) == "v"
