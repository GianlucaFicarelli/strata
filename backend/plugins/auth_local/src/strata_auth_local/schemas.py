"""Pydantic schemas for the auth_local plugin."""

from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /api/plugins/auth_local/login``.

    Attributes:
        username: The account's login handle.
        password: The account's plaintext password (transmitted over HTTPS
            only; never stored).
    """

    username: Annotated[str, Field(min_length=1, max_length=255)]
    password: Annotated[str, Field(min_length=1)]


class InviteCreateRequest(BaseModel):
    """Body for ``POST /api/admin/auth_local/invites``.

    Attributes:
        expires_in_hours: How many hours until the invite link expires.
            Defaults to 48 hours.
    """

    expires_in_hours: Annotated[int, Field(default=48, ge=1, le=168)]


class InviteCreateResponse(BaseModel):
    """Response from ``POST /api/admin/auth_local/invites``.

    The raw token is returned exactly once.  It is not stored server-side
    (only the SHA-256 hash is persisted).

    Attributes:
        invite_id: The ``core_invites.id`` UUID.
        token: The raw invite token to embed in the invite URL.  Shown once.
        expires_in_hours: Lifetime of the invite in hours.
    """

    invite_id: Annotated[str, Field(description="core_invites.id UUID")]
    token: Annotated[str, Field(description="Raw invite token — share this once")]
    expires_in_hours: int


class InviteAcceptRequest(BaseModel):
    """Body for ``POST /api/plugins/auth_local/invite/{token}/accept``.

    Attributes:
        username: Desired login handle — must be unique across all local users.
        display_name: Human-readable name stored in ``core_users``.
        email: Optional email address stored in ``core_users``.
        password: Chosen password; hashed with Argon2id before storage.
    """

    username: Annotated[str, Field(min_length=1, max_length=255)]
    display_name: Annotated[str, Field(min_length=1, max_length=255)]
    email: Annotated[str | None, Field(default=None)]
    password: Annotated[str, Field(min_length=8)]


class UserResponse(BaseModel):
    """Public profile returned after login or registration.

    Attributes:
        id: ``core_users.id`` UUID.
        username: Login handle.
        display_name: Human-readable name.
        email: Optional email.
        is_admin: Platform admin flag.
    """

    id: Annotated[str, Field(description="core_users.id UUID")]
    username: Annotated[str, Field(description="Login handle")]
    display_name: Annotated[str, Field(description="Human-readable name")]
    email: Annotated[str | None, Field(default=None)]
    is_admin: Annotated[bool, Field(default=False)]
