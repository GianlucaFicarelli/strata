"""Unit tests for strata_jwt_auth.utils.

All tests are pure-Python, no DB or HTTP needed.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from strata_jwt_auth.config import settings
from strata_jwt_auth.utils import (
    auth_user_from_token,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    user_to_auth_user,
    verify_password,
)

# ── Password helpers ──────────────────────────────────────────────────────────


def test_hash_password_returns_string():
    h = hash_password("secret123")
    assert isinstance(h, str)
    assert len(h) > 20


def test_verify_password_correct():
    h = hash_password("correct_password")
    assert verify_password("correct_password", h) is True


def test_verify_password_wrong():
    h = hash_password("right")
    assert verify_password("wrong", h) is False


def test_hash_password_is_unique_per_call():
    # Argon2 uses a random salt — same plaintext should produce different hashes.
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


# ── JWT access token ──────────────────────────────────────────────────────────


def _make_user(**kwargs) -> SimpleNamespace:
    """Build a lightweight stand-in for a User ORM row.

    ``create_access_token`` and ``user_to_auth_user`` only read ``.id``,
    ``.username``, and ``.is_admin`` — no DB access needed.
    """
    defaults = {
        "id": "test-uuid-1234",
        "username": "alice",
        "hashed_password": "x",
        "is_admin": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_create_access_token_is_decodable(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", 15, raising=False)

    token = create_access_token(_make_user())
    payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert payload["username"] == "alice"
    assert payload["sub"] == "test-uuid-1234"
    assert payload["is_admin"] is False


def test_decode_access_token_valid(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", 15, raising=False)

    token = create_access_token(_make_user())
    payload = decode_access_token(token)
    assert payload["username"] == "alice"


def test_decode_access_token_expired_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256", raising=False)

    expired_payload = {
        "sub": "uid",
        "username": "bob",
        "is_admin": False,
        "exp": datetime.now(UTC) - timedelta(seconds=1),
    }
    token = jwt.encode(expired_payload, "test-secret", algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_decode_access_token_invalid_signature_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "real-secret", raising=False)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", 15, raising=False)

    token = create_access_token(_make_user())

    # Tamper with the signature
    parts = token.split(".")
    parts[-1] = parts[-1][:-4] + "XXXX"
    bad_token = ".".join(parts)

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(bad_token)
    assert exc_info.value.status_code == 401


def test_auth_user_from_token(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", 15, raising=False)

    token = create_access_token(_make_user(is_admin=True))
    user = auth_user_from_token(token)
    assert user.id == "test-uuid-1234"
    assert user.username == "alice"
    assert user.is_admin is True


# ── Refresh token helpers ─────────────────────────────────────────────────────


def test_generate_refresh_token_returns_tuple():
    raw, h = generate_refresh_token()
    assert isinstance(raw, str)
    assert isinstance(h, str)


def test_generate_refresh_token_hash_is_sha256_hex():
    _, h = generate_refresh_token()
    assert len(h) == 64
    int(h, 16)  # must be valid hex


def test_hash_refresh_token_deterministic():
    raw = "fixed_raw_token"
    assert hash_refresh_token(raw) == hash_refresh_token(raw)


def test_hash_refresh_token_matches_generate():
    raw, expected_hash = generate_refresh_token()
    assert hash_refresh_token(raw) == expected_hash


def test_refresh_token_expiry_in_future(monkeypatch):
    monkeypatch.setattr(settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)
    expiry = refresh_token_expiry()
    assert expiry > datetime.now(UTC)


def test_refresh_token_expiry_approx_30_days(monkeypatch):
    monkeypatch.setattr(settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)
    expiry = refresh_token_expiry()
    delta = expiry - datetime.now(UTC)
    # Allow a small window for test execution time
    assert 29.99 < delta.total_seconds() / 86400 <= 30.01


# ── user_to_auth_user ─────────────────────────────────────────────────────────


def test_user_to_auth_user_maps_fields():
    u = _make_user(id="abc", username="bob", is_admin=True)
    auth = user_to_auth_user(u)
    assert auth.id == "abc"
    assert auth.username == "bob"
    assert auth.is_admin is True
