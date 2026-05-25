"""Storage backend dependency.

Resolves the ``?backend=<id>`` query parameter to a StorageBackend instance.
The backend is always a ``core_storage_instances`` UUID; the requesting user's
identity is taken from the session cookie (via :data:`CurrentUserDep`).

A second helper :func:`resolve_backend_by_ids` is provided for the download
endpoint, which authenticates via a signed download token instead of a
session cookie and therefore supplies ``user_id`` and ``username`` directly.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageTemplateRegistryDep
from strata.plugins.protocols import StorageBackend
from strata.plugins.registry import StorageTemplateRegistry
from strata.storage import service


async def resolve_backend_by_ids(
    db_session: AsyncSession,
    *,
    instance_id: str,
    user_id: str,
    template_registry: StorageTemplateRegistry,
) -> StorageBackend | None:
    """Resolve a backend directly from IDs without a FastAPI dependency.

    Used by the download endpoint, which authenticates via an HMAC token
    rather than a session cookie.  The token embeds ``user_id`` and
    ``backend_id`` so no ``CurrentUserDep`` is available.

    Because the download token does not carry a ``username`` (it's kept
    minimal for URL-safety), the ``user_id`` is used as the username
    placeholder in path template expansion.  This is acceptable for
    download-only access; writes always go through the session-authenticated
    path where the full ``username`` is available.

    Args:
        db_session: Async SQLAlchemy session.
        instance_id: ``core_storage_instances.id`` UUID.
        user_id: ``core_users.id`` UUID from the verified download token.
        template_registry: Registered storage templates.

    Returns:
        A :class:`~strata.plugins.protocols.StorageBackend`, or ``None`` if
        the backend is not found or not ready for this user.
    """
    return await service.resolve_backend_for_user(
        db_session,
        instance_id=instance_id,
        user_id=user_id,
        username=user_id,  # placeholder: download tokens carry no username
        template_registry=template_registry,
    )


async def storage_backend_dep(
    template_registry: StorageTemplateRegistryDep,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
    backend: Annotated[str, Query(description="Instance UUID")],
) -> StorageBackend:
    """Resolve ``?backend=<id>`` to a StorageBackend for the current user.

    Args:
        template_registry: Registered storage templates.
        session: Async DB session.
        current_user: Authenticated user from the session cookie.
        backend: ``core_storage_instances.id`` UUID from the query string.

    Returns:
        The resolved :class:`~strata.plugins.protocols.StorageBackend`.

    Raises:
        HTTPException: 400 if the backend is not found or not ready.
    """
    resolved = await service.resolve_backend_for_user(
        session,
        instance_id=backend,
        user_id=current_user.id,
        username=current_user.username,
        template_registry=template_registry,
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backend {backend!r} not found or not available for this user",
        )
    return resolved


StorageBackendDep = Annotated[StorageBackend, Depends(storage_backend_dep)]
