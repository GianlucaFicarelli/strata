"""Generic authentication routes for Strata.

These routes are provided by the *core* — they are always available
regardless of which auth plugins are loaded.  They are deliberately thin:
no auth logic lives here.

Routes
------
GET  /api/auth/providers
    Return a list of available authentication providers with enough metadata
    for the frontend to build a login form (login URL, display name, etc.).

GET  /api/auth/me
    Return the currently authenticated user's profile.  Requires a valid
    ``strata_session`` HttpOnly cookie (set by the active auth plugin on
    login).  The session is looked up in Redis by
    :data:`~strata.dependencies.auth.CurrentUserDep`.
"""

from typing import Any

from fastapi import APIRouter

from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.registry import AuthRegistryDep
from strata.schemas.auth import AuthUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/providers")
def list_auth_providers(auth_registry: AuthRegistryDep) -> list[dict[str, Any]]:
    """Return metadata for every registered auth provider.

    The frontend uses this to determine which login UI to show.  Each entry
    includes at minimum ``id``, ``name``, and ``login_url``.  Providers may
    expose additional metadata by implementing
    :meth:`~strata.plugins.protocols.AuthProvider.describe`.

    Returns:
        A list of provider description dicts, one per registered provider.
    """
    return [provider.describe() for provider in auth_registry.all()]


@router.get("/me")
def get_current_user(current_user: CurrentUserDep) -> AuthUser:
    """Return the authenticated user's public profile.

    Reads the ``strata_session`` cookie and looks up the session in Redis.
    Provider-agnostic: works with any active auth plugin.

    Returns:
        The :class:`~strata.schemas.auth.AuthUser` for the current session.

    Raises:
        HTTPException: 401 if the session cookie is absent or expired.
    """
    return current_user
