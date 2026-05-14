from typing import Annotated

from fastapi import Depends, Query

from strata.dependencies.registry import StorageRegistryDep
from strata.plugins.protocols import StorageBackend


def storage_backend_dep(
    storage_registry: StorageRegistryDep,
    backend: Annotated[str, Query(description="Backend id")],
) -> StorageBackend:
    return storage_registry.get(backend_id=backend)


StorageBackendDep = Annotated[StorageBackend, Depends(storage_backend_dep)]
