"""Unit tests for strata.tokens — HMAC download token signing and verification."""

import time

import pytest

from strata.tokens import issue_download_token, verify_download_token


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    monkeypatch.setenv("STRATA_ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")
    # Force settings reload so the env var is picked up
    import importlib
    import strata.config as cfg
    importlib.reload(cfg)
    import strata.tokens as tok
    importlib.reload(tok)


def test_round_trip():
    """issue → verify returns the correct (user_id, backend_id)."""
    from strata.tokens import issue_download_token, verify_download_token
    token = issue_download_token(user_id="uid-1", backend_id="bid-2")
    user_id, backend_id = verify_download_token(token)
    assert user_id == "uid-1"
    assert backend_id == "bid-2"


def test_tampered_signature_raises_401():
    from strata.tokens import issue_download_token, verify_download_token
    from fastapi import HTTPException
    token = issue_download_token("u", "b")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(HTTPException) as exc_info:
        verify_download_token(tampered)
    assert exc_info.value.status_code == 401


def test_expired_token_raises_401(monkeypatch):
    """A token with an exp in the past is rejected."""
    from strata.tokens import issue_download_token, verify_download_token
    from fastapi import HTTPException
    import strata.config as cfg
    monkeypatch.setattr(cfg.settings, "DOWNLOAD_TOKEN_TTL_SECONDS", -10)
    token = issue_download_token("u", "b")
    with pytest.raises(HTTPException) as exc_info:
        verify_download_token(token)
    assert exc_info.value.status_code == 401


def test_empty_token_raises_401():
    from strata.tokens import verify_download_token
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        verify_download_token("")


def test_malformed_token_raises_401():
    from strata.tokens import verify_download_token
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        verify_download_token("no-dot-separator-at-all")


def test_tokens_are_distinct():
    """Two tokens for the same user+backend issued a second apart differ."""
    from strata.tokens import issue_download_token
    t1 = issue_download_token("u", "b")
    time.sleep(1.1)
    t2 = issue_download_token("u", "b")
    assert t1 != t2
