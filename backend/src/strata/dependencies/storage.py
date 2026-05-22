"""Storage backend dependency.

Resolves the ``?backend=<id>`` query parameter to a StorageBackend instance.

Resolution order:
1. Check ``StorageRegistry`` for a directly registered backend (plugin singletons).
2. Check ``core_storage_instances`` DB table for an instance UUID → construct
   via the matching ``StorageTemplate`` with the requesting user's context.

An unauthenticated request can only access directly registered backends.
Instance-backed backends require authentication (the user identity is needed
for template expansion and user-config merging).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status

from strata.dependencies.auth import CurrentUserDep
from strata.dependencies.db import AsyncSessionDep
from strata.dependencies.registry import StorageRegistryDep, StorageTemplateRegistryDep
from strata.plugins.protocols import StorageBackend
from strata.storage import service


async def storage_backend_dep(
    storage_registry: StorageRegistryDep,
    template_registry: StorageTemplateRegistryDep,
    session: AsyncSessionDep,
    current_user: CurrentUserDep,
    backend: Annotated[str, Query(description="Backend id or instance UUID")],
) -> StorageBackend:
    """Resolve ``?backend=<id>`` to a StorageBackend.

    Tries the static registry first, then instance lookup.
    """
    # 1. Static registry (plugin singletons)
    if storage_registry._backends.get(backend):
        return storage_registry.get(backend_id=backend)

    # 2. Instance-backed lookup requires authentication
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access storage instances",
        )

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
