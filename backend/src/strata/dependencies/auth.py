"""Authentication dependencies.

Two generic auth dependencies are provided, both backend-agnostic:

:data:`OptionalCurrentUserDep`
    Resolves to the authenticated :class:`~strata.schemas.auth.AuthUser`
    if a valid ``Authorization: Bearer`` token is present, or ``None`` if the
    header is absent or no auth plugin is loaded.  Use this for endpoints that
    work for both anonymous and authenticated callers (e.g. public reads).

:data:`CurrentUserDep`
    Like ``OptionalCurrentUserDep`` but raises **HTTP 401** when no valid
    token is present.  Use this for endpoints that require authentication.

The core never imports any specific auth plugin.  Token verification is delegated
to :meth:`~strata.plugins.registry.AuthRegistry.verify_token`, which tries
each registered ``AuthProvider`` in order.  Swapping JWT for OIDC or adding
a second provider requires no changes here.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from strata.dependencies.registry import AuthRegistryDep
from strata.schemas.auth import AuthUser

# HTTPBearer with auto_error=False so we can return None for unauthenticated
# requests rather than raising immediately.  The require_* variant does the
# 401 raise itself after checking all providers.
_bearer = HTTPBearer(auto_error=False)


async def optional_current_user_dep(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth_registry: AuthRegistryDep,
) -> AuthUser | None:
    """Return the authenticated user if a valid bearer token is present.

    Tries every registered ``AuthProvider.verify_token()`` in order.
    Returns ``None`` when:

    - No ``Authorization`` header is present.
    - No auth plugin is loaded.
    - No provider recognises the token (all returned ``None``).

    Raises HTTP 401 when a provider explicitly rejects the token (expired,
    tampered, etc.).

    Args:
        credentials: Parsed ``Authorization: Bearer <token>`` header, or
            ``None`` if the header is absent.
        auth_registry: The application-wide auth provider registry.

    Returns:
        The authenticated :class:`~strata.plugins.protocols.AuthUser`, or
        ``None``.
    """
    if credentials is None:
        return None
    return await auth_registry.verify_token(credentials.credentials)


async def require_current_user_dep(
    user: Annotated[AuthUser | None, Depends(optional_current_user_dep)],
) -> AuthUser:
    """Return the authenticated user or raise HTTP 401.

    Wraps :func:`optional_current_user_dep` and raises when no valid user
    could be resolved.  Use this on endpoints that must be authenticated.

    Args:
        user: Result of ``optional_current_user_dep``.

    Returns:
        The authenticated :class:`~strata.plugins.protocols.AuthUser`.

    Raises:
        HTTPException: 401 if no valid bearer token was provided.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


OptionalCurrentUserDep = Annotated[AuthUser | None, Depends(optional_current_user_dep)]
CurrentUserDep = Annotated[AuthUser, Depends(require_current_user_dep)]
