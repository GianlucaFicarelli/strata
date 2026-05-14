from pydantic import BaseModel


class AuthUser(BaseModel):
    """Minimal representation of an authenticated user.

    The ``id`` field is always the corresponding ``core_users.id`` UUID.
    This is the stable cross-plugin identity: any plugin that stores
    per-user data should use this value as its ``user_id`` foreign key.

    Attributes:
        id: Opaque UUID string; corresponds to ``core_users.id``.
        username: Display name or login handle.
        is_admin: ``True`` if the user has administrative privileges.
    """

    id: str
    username: str
    is_admin: bool = False
