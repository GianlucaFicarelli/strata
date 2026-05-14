"""JWT and password utilities for the jwt_auth plugin.

Responsibilities
----------------
- Sign and decode short-lived **access tokens** (PyJWT / HS256).
- Issue, hash, and verify long-lived **refresh tokens** (random bytes, SHA-256).
- Hash and verify **passwords** (Argon2id via pwdlib).
- Convert a DB :class:`~strata_jwt_auth.models.User` to a protocol
  :class:`~strata.plugins.protocols.AuthUser`.

Nothing in this module touches the database directly; all DB work happens in
:mod:`strata_jwt_auth.router`.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from strata.schemas.auth import AuthUser
from strata_jwt_auth.config import settings
from strata_jwt_auth.models import User

_password_hash = PasswordHash.recommended()


# ── Password helpers ──────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Return an Argon2id hash of *plain*.

    Args:
        plain: Plain-text password supplied by the user.

    Returns:
        Argon2id hash string suitable for storage in the database.
    """
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches the stored *hashed* password.

    Args:
        plain: Plain-text password to verify.
        hashed: Stored Argon2id hash from the database.

    Returns:
        ``True`` if the password is correct, ``False`` otherwise.
    """
    return _password_hash.verify(plain, hashed)


# ── Access token helpers ──────────────────────────────────────────────────────


def create_access_token(user: User) -> str:
    """Return a signed JWT access token for *user*.

    The token embeds ``sub`` (user id), ``username``, ``is_admin``, and
    ``exp`` (expiry).  No sensitive data is stored in the payload.

    Args:
        user: The authenticated :class:`~strata_jwt_auth.models.User` row.

    Returns:
        A compact, URL-safe JWT string.
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: Compact JWT string from the ``Authorization: Bearer`` header.

    Returns:
        The decoded payload dict.

    Raises:
        HTTPException: 401 if the token is malformed, expired, or has an
            invalid signature.
    """
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def auth_user_from_token(token: str) -> AuthUser:
    """Decode *token* and return the corresponding :class:`~strata.plugins.protocols.AuthUser`.

    Convenience wrapper used by protected route dependencies.

    Args:
        token: Compact JWT string.

    Returns:
        An :class:`~strata.plugins.protocols.AuthUser` built from the token payload.

    Raises:
        HTTPException: 401 on any token error (see :func:`decode_access_token`).
    """
    payload = decode_access_token(token)
    return AuthUser(
        id=payload["sub"],
        username=payload["username"],
        is_admin=payload.get("is_admin", False),
    )


def user_to_auth_user(user: User) -> AuthUser:
    """Convert a DB :class:`~strata_jwt_auth.models.User` to an :class:`~strata.plugins.protocols.AuthUser`.

    Args:
        user: ORM user row.

    Returns:
        Protocol-level :class:`~strata.plugins.protocols.AuthUser`.
    """  # noqa: E501
    return AuthUser(id=user.id, username=user.username, is_admin=user.is_admin)


# ── Refresh token helpers ─────────────────────────────────────────────────────


def generate_refresh_token() -> tuple[str, str]:
    """Generate a cryptographically random refresh token.

    Returns:
        A ``(raw_token, token_hash)`` tuple.  Send *raw_token* to the client
        (e.g. as an ``HttpOnly`` cookie).  Store *token_hash* in the DB.
        Never store the raw token.
    """
    raw = secrets.token_hex(32)
    token_hash = hash_refresh_token(raw)
    return raw, token_hash


def hash_refresh_token(raw: str) -> str:
    """Return the SHA-256 hex digest of *raw*.

    Args:
        raw: The plain-text refresh token as returned by :func:`generate_refresh_token`.

    Returns:
        64-character hex string stored in ``jwt_auth_refresh_tokens.token_hash``.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    """Return the UTC expiry datetime for a newly issued refresh token.

    Returns:
        ``now + STRATA_JWT_REFRESH_EXPIRE_DAYS`` in UTC.
    """
    return datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
