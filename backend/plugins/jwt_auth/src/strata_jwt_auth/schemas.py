"""Pydantic request/response schemas for the JWT auth plugin."""

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    """Request body for ``POST /api/plugins/jwt_auth/register``.

    Attributes:
        username: Desired login name.  1-255 characters, no leading/trailing
            whitespace.
        password: Plain-text password.  Must be at least 8 characters.
            Hashed with Argon2id before storage; never persisted in plain text.
    """

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)

    @field_validator("username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip()


class LoginResponse(BaseModel):
    """Response body for a successful ``POST /api/plugins/jwt_auth/login``.

    Attributes:
        access_token: Short-lived signed JWT.  Include in subsequent requests
            as ``Authorization: Bearer <access_token>``.
        refresh_token: Long-lived opaque token.  Store in an ``HttpOnly``
            cookie and use it with ``POST /api/plugins/jwt_auth/refresh`` to
            obtain a new access token without re-entering credentials.
        token_type: Always ``"bearer"``.
        expires_in: Access token lifetime in seconds.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Request body for ``POST /api/plugins/jwt_auth/refresh``.

    Attributes:
        refresh_token: The opaque refresh token previously returned by login.
    """

    refresh_token: str


class UserResponse(BaseModel):
    """Public representation of a user, returned by ``GET /api/plugins/jwt_auth/me``.

    Attributes:
        id: Opaque UUID string.
        username: Login name.
        is_admin: ``True`` if the user has administrative privileges.
    """

    id: str
    username: str
    is_admin: bool
