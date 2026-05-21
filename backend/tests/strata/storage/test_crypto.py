"""Unit tests for strata.crypto."""

import base64

import pytest

from strata.crypto import decrypt_field, encrypt_field


def _key() -> str:
    return base64.urlsafe_b64encode(b"K" * 32).decode()


def test_roundtrip():
    key = _key()
    plain = "hunter2"
    token = encrypt_field(plain, key)
    assert decrypt_field(token, key) == plain


def test_different_nonces_each_call():
    key = _key()
    t1 = encrypt_field("same", key)
    t2 = encrypt_field("same", key)
    assert t1 != t2  # different random nonces


def test_wrong_key_raises():
    key1 = base64.urlsafe_b64encode(b"A" * 32).decode()
    key2 = base64.urlsafe_b64encode(b"B" * 32).decode()
    token = encrypt_field("secret", key1)
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_field(token, key2)


def test_invalid_key_length_raises():
    bad_key = base64.urlsafe_b64encode(b"short").decode()
    with pytest.raises(ValueError):
        encrypt_field("x", bad_key)


def test_tampered_ciphertext_raises():
    key = _key()
    token = encrypt_field("data", key)
    raw = base64.urlsafe_b64decode(token + "==")
    tampered = base64.urlsafe_b64encode(raw[:-1] + bytes([raw[-1] ^ 0xFF])).decode()
    with pytest.raises(ValueError):
        decrypt_field(tampered, key)


def test_empty_string_roundtrip():
    key = _key()
    assert decrypt_field(encrypt_field("", key), key) == ""


def test_unicode_roundtrip():
    key = _key()
    plain = "密码 🔑"
    assert decrypt_field(encrypt_field(plain, key), key) == plain
