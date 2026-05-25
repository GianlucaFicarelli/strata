"""Session data structures."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionData:
    """Data stored in Redis for a single authenticated session.

    All fields are sourced from the auth provider and ``core_users`` at login
    time.  Storing them here avoids a DB query on every request while still
    reflecting the current user state for the session lifetime.

    Attributes:
        user_id: ``core_users.id`` UUID — stable identity key.
        username: Login name from the active auth provider (used for storage
            path template expansion and display).
        display_name: Human-readable name (from ``core_users.display_name``).
        email: Optional email (from ``core_users.email``).
        is_admin: Platform admin flag (from ``core_users.is_admin``).
    """

    user_id: str
    username: str
    display_name: str
    email: str | None
    is_admin: bool
