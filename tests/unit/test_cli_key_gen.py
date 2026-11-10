"""`yf key-gen`: print a usable master key to stdout and never touch .env."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from cli import main
from core.crypto import SecretBox


def _run(capsys, argv):
    code = main(argv)
    out = capsys.readouterr().out
    return code, out


@pytest.mark.parametrize("size", [16, 24, 32])
def test_key_gen_prints_a_usable_key(capsys, size):
    code, out = _run(capsys, ["key-gen", "--bytes", str(size)])
    assert code == 0
    key = out.strip()
    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    assert len(raw) == size
    box = SecretBox(key_b64=key)
    assert box.decrypt(box.encrypt("v", aad=b"email_refresh_token"), aad=b"email_refresh_token") == "v"


def test_key_gen_default_is_32_bytes_and_urlsafe(capsys):
    code, out = _run(capsys, ["key-gen"])
    assert code == 0
    key = out.strip()
    assert len(key) == 44  # 32 bytes -> 44 urlsafe-base64 chars with padding
    assert "+" not in key and "/" not in key
    SecretBox(key_b64=key)


def test_key_gen_is_fresh_every_call(capsys):
    _, first = _run(capsys, ["key-gen"])
    _, second = _run(capsys, ["key-gen"])
    assert first.strip() != second.strip()


def test_key_gen_rejects_bad_size(capsys):
    with pytest.raises(SystemExit):
        main(["key-gen", "--bytes", "20"])


def test_key_gen_does_not_touch_env_file(capsys, monkeypatch, tmp_path):
    """It must not read or write .env: the operator pastes the value themselves."""
    fake_env = tmp_path / ".env"
    fake_env.write_text("YF_MASTER_KEY=placeholder\n", encoding="utf-8")
    before = fake_env.read_bytes()
    monkeypatch.setenv("YF_MASTER_KEY", "irrelevant-for-key-gen")
    code, out = _run(capsys, ["key-gen"])
    assert code == 0
    assert SecretBox(key_b64=out.strip())
    assert fake_env.read_bytes() == before
    assert Path(fake_env).stat().st_size == len(before)


def test_generate_master_key_rejects_bad_byte_length():
    from core.crypto import generate_master_key

    with pytest.raises(ValueError):
        generate_master_key(20)
