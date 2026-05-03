from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from strata_jwt_auth.config import settings


def _create_access_token(user_id: str, username: str, is_admin: bool) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: Opaque user identifier (database primary key).
        username: Username or email to embed in the token.
        is_admin: Whether the user has admin privileges.

    Returns:
        A signed JWT string.
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: Signed JWT string.

    Returns:
        The decoded payload dict.

    Raises:
        HTTPException: 401 if the token is invalid or expired.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
