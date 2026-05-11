"""FastAPI dependency functions for Strata.

All application-wide ``Depends`` helpers live here.  Plugin routes should
import from this module rather than reaching into ``request.state`` directly.

Authentication dependencies
---------------------------
Two generic auth dependencies are provided, both backend-agnostic:

:data:`OptionalCurrentUserDep`
    Resolves to the authenticated :class:`~strata.plugins.protocols.AuthUser`
    if a valid ``Authorization: Bearer`` token is present, or ``None`` if the
    header is absent or no auth plugin is loaded.  Use this for endpoints that
    work for both anonymous and authenticated callers (e.g. public reads).

:data:`CurrentUserDep`
    Like ``OptionalCurrentUserDep`` but raises **HTTP 401** when no valid
    token is present.  Use this for endpoints that require authentication.

The core never imports ``jwt_auth`` or any other auth plugin.  Token
verification is delegated to
:meth:`~strata.plugins.registry.AuthRegistry.verify_token`, which tries
each registered ``AuthProvider`` in order.  Swapping JWT for OIDC or adding
a second provider requires no changes here.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.db.session import session_scope
from strata.plugins.protocols import AuthUser, StorageBackend
from strata.plugins.registry import (
    AuthRegistry,
    FileHandlerRegistry,
    PluginRegistry,
    StorageRegistry,
)

# ── Registry dependencies ─────────────────────────────────────────────────────


def plugin_registry_dep(request: Request) -> PluginRegistry:
    return request.state.plugin_registry


def storage_registry_dep(
    plugin_registry: Annotated[PluginRegistry, Depends(plugin_registry_dep)],
) -> StorageRegistry:
    return plugin_registry.storage


def file_handlers_registry_dep(
    plugin_registry: Annotated[PluginRegistry, Depends(plugin_registry_dep)],
) -> FileHandlerRegistry:
    return plugin_registry.file_handlers


def auth_registry_dep(
    plugin_registry: Annotated[PluginRegistry, Depends(plugin_registry_dep)],
) -> AuthRegistry:
    return plugin_registry.auth


def storage_backend_dep(
    storage_registry: Annotated[StorageRegistry, Depends(storage_registry_dep)],
    backend: Annotated[str, Query(description="Backend id")],
) -> StorageBackend:
    return storage_registry.get(backend_id=backend)


# ── Database dependencies ─────────────────────────────────────────────────────


def session_factory_dep(request: Request) -> async_sessionmaker[AsyncSession]:
    """Extract the session factory from ``request.state``."""
    return request.state.db_session_factory


async def db_session_dep(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(session_factory_dep)],
) -> AsyncGenerator[AsyncSession]:
    """Yield one :class:`~sqlalchemy.ext.asyncio.AsyncSession` per request.

    Commits on success, rolls back on any unhandled exception.
    """
    async with session_scope(session_factory) as session:
        yield session


# ── Authentication dependencies ───────────────────────────────────────────────

# HTTPBearer with auto_error=False so we can return None for unauthenticated
# requests rather than raising immediately.  The require_* variant does the
# 401 raise itself after checking all providers.
_bearer = HTTPBearer(auto_error=False)


async def optional_current_user_dep(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth_registry: Annotated[AuthRegistry, Depends(auth_registry_dep)],
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


# ── Type aliases ──────────────────────────────────────────────────────────────

StorageRegistryDep = Annotated[StorageRegistry, Depends(storage_registry_dep)]
FileHandlerRegistryDep = Annotated[FileHandlerRegistry, Depends(file_handlers_registry_dep)]
StorageBackendDep = Annotated[StorageBackend, Depends(storage_backend_dep)]
AsyncSessionDep = Annotated[AsyncSession, Depends(db_session_dep, scope="function")]
OptionalCurrentUserDep = Annotated[AuthUser | None, Depends(optional_current_user_dep)]
CurrentUserDep = Annotated[AuthUser, Depends(require_current_user_dep)]
