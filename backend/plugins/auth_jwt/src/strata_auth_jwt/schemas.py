"""Pydantic request/response schemas for the JWT auth plugin."""

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    """Request body for ``POST /api/plugins/auth_jwt/register``.

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
    """Response body for a successful ``POST /api/plugins/auth_jwt/login``
    or ``POST /api/plugins/auth_jwt/refresh``.

    Attributes:
        access_token: Short-lived signed JWT.  Include in subsequent requests
            as ``Authorization: Bearer <access_token>``.
        token_type: Always ``"bearer"``.
        expires_in: Access token lifetime in seconds.

    Note:
        The refresh token is delivered as an ``HttpOnly`` cookie named
        ``strata_refresh_token`` and is therefore absent from this body.
        Storing it in the response body would expose it to JavaScript.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Optional request body for ``POST /api/plugins/auth_jwt/refresh``.

    The preferred path reads the refresh token from the ``strata_refresh_token``
    HttpOnly cookie (sent automatically by the browser).  This body field is
    accepted as a fallback so that the OpenAPI ``/docs`` UI — which cannot set
    cookies — can still exercise the endpoint.

    Attributes:
        refresh_token: The opaque refresh token.  Omit when using the cookie.
    """

    refresh_token: str | None = None


class UserResponse(BaseModel):
    """Public representation of a user, returned by ``GET /api/plugins/auth_jwt/me``.

    Attributes:
        id: Opaque UUID string.
        username: Login name.
        is_admin: ``True`` if the user has administrative privileges.
    """

    id: str
    username: str
    is_admin: bool
