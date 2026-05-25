from typing import Annotated

from pydantic import BaseModel, Field


class AuthUser(BaseModel):
    """Authenticated user resolved from a session.

    The ``id`` field is always the corresponding ``core_users.id`` UUID.
    This is the stable cross-plugin identity: any plugin that stores
    per-user data should use this value as its ``user_id`` foreign key.

    ``username`` is the login credential as known to the auth provider
    (e.g. the value from ``auth_local_users.username``, or the
    ``preferred_username`` claim from an OIDC provider).  It is used for
    storage path template expansion (``{username}``) and display.

    Attributes:
        id: Opaque UUID string; corresponds to ``core_users.id``.
        username: Login name from the active auth provider.
        display_name: Human-readable name from ``core_users.display_name``.
        email: Optional email address from ``core_users.email``.
        is_admin: ``True`` if the user has administrative privileges.
    """

    id: Annotated[str, Field(description="core_users.id UUID")]
    username: Annotated[str, Field(description="Login name from the auth provider")]
    display_name: Annotated[str, Field(description="Human-readable display name")]
    email: Annotated[str | None, Field(default=None, description="Optional email address")]
    is_admin: Annotated[bool, Field(default=False, description="Platform admin flag")]
