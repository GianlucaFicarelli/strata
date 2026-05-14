"""Generic authentication routes for Strata.

These routes are provided by the *core* — they are always available
regardless of which auth plugins are loaded.  They are deliberately thin:
no auth logic lives here.  Everything is delegated to the registered
``AuthProvider`` implementations via the ``AuthRegistry``.

Routes
------
GET  /api/auth/providers
    Return a list of available authentication providers, with enough
    metadata for the frontend to build a login form.

GET  /api/auth/me
    Return the currently authenticated user's profile.  Requires a valid
    bearer token (from any registered provider).
"""

from fastapi import APIRouter

from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.registry import AuthRegistryDep
from strata.schemas.auth import AuthUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/providers")
def list_auth_providers(auth_registry: AuthRegistryDep) -> list[dict]:
    """Return metadata for every registered auth provider.

    The frontend uses this to determine which login UI to show.  Each
    entry includes at minimum ``id`` and ``name``.  Providers may expose
    additional metadata (e.g. ``login_url``, ``scopes``) by implementing
    :meth:`~strata.plugins.protocols.AuthProvider.describe`.

    Returns:
        A list of provider description dicts, one per registered provider.
    """
    return [provider.describe() for provider in auth_registry.all()]


@router.get("/me")
def get_current_user(current_user: CurrentUserDep) -> AuthUser:
    """Return the authenticated user's public profile.

    This endpoint is provider-agnostic: any registered ``AuthProvider``
    that implements :meth:`~strata.plugins.protocols.AuthProvider.verify_token`
    can satisfy the dependency.

    Returns:
        The :class:`~strata.plugins.protocols.AuthUser` extracted from the
        bearer token.

    Raises:
        HTTPException: 401 if no valid bearer token is present.
    """
    return current_user
