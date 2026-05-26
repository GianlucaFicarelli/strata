"""Unit tests for strata.tokens — HMAC download token signing and verification."""

import pytest
from fastapi import HTTPException

import strata.config as cfg
from strata.tokens import issue_download_token, verify_download_token

_TEST_KEY = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ="


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    monkeypatch.setattr(cfg.settings, "ENCRYPTION_KEY", _TEST_KEY)


def test_round_trip():
    """issue → verify returns the correct (user_id, backend_id)."""
    token = issue_download_token(user_id="uid-1", backend_id="bid-2")
    user_id, backend_id = verify_download_token(token)
    assert user_id == "uid-1"
    assert backend_id == "bid-2"


def test_tampered_signature_raises_401():
    token = issue_download_token("u", "b")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(HTTPException) as exc_info:
        verify_download_token(tampered)
    assert exc_info.value.status_code == 401


def test_expired_token_raises_401(monkeypatch):
    """A token with an exp in the past is rejected."""
    monkeypatch.setattr(cfg.settings, "DOWNLOAD_TOKEN_TTL_SECONDS", -10)
    token = issue_download_token("u", "b")
    with pytest.raises(HTTPException) as exc_info:
        verify_download_token(token)
    assert exc_info.value.status_code == 401


def test_empty_token_raises_401():
    with pytest.raises(HTTPException):
        verify_download_token("")


def test_malformed_token_raises_401():
    with pytest.raises(HTTPException):
        verify_download_token("no-dot-separator-at-all")


def test_tokens_are_distinct(monkeypatch):
    """Two tokens for the same user+backend issued at different times differ."""
    times = iter([1_000_000.0, 1_000_001.0])
    monkeypatch.setattr("strata.tokens.time.time", lambda: next(times))

    t1 = issue_download_token("u", "b")
    t2 = issue_download_token("u", "b")
    assert t1 != t2
