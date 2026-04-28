"""Storage backend registry for Strata.

Maintains the mapping of backend IDs to ``StorageBackend`` instances.
The local backend is always present.  Plugins register additional
backends at startup via ``register()``.
"""

from typing import TYPE_CHECKING

from fastapi import HTTPException, Query

from strata.core.storage.local import local_storage

if TYPE_CHECKING:
    from strata.core.storage.base import StorageBackend

#: All registered backends, keyed by their ``id``.
_backends: dict[str, StorageBackend] = {
    local_storage.id: local_storage,
}


def register(backend: StorageBackend) -> None:
    """Add a storage backend to the registry.

    If a backend with the same ``id`` is already registered it will be
    replaced.  Called automatically for every plugin that returns a
    non-``None`` value from ``get_storage_backend()``.

    Args:
        backend: The ``StorageBackend`` instance to register.

    """
    _backends[backend.id] = backend
    print(f"[storage-registry] Registered backend: {backend.id} ({backend.name})")


def get_all() -> list[StorageBackend]:
    """Return every registered backend.

    Returns:
        A list of ``StorageBackend`` instances in registration order.

    """
    return list(_backends.values())


def get(backend_id: str) -> StorageBackend:
    """Look up a backend by its id.

    Args:
        backend_id: The ``id`` attribute of the desired backend.

    Returns:
        The matching ``StorageBackend`` instance.

    Raises:
        HTTPException: 400 if *backend_id* is not registered.

    """
    try:
        return _backends[backend_id]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown backend '{backend_id}'. Available: {list(_backends)}",
        ) from None


def backend_dep(
    backend: str = Query(default="local", description="Storage backend ID"),
) -> StorageBackend:
    """FastAPI dependency that resolves ``?backend=<id>`` to a backend instance.

    Inject this with ``Depends(backend_dep)`` in any route that needs to
    delegate to the caller-selected storage backend.

    Example::

        @router.get("/list")
        async def list_dir(path: str, storage: StorageBackend = Depends(backend_dep)):
            return await storage.list(path)

    Args:
        backend: Value of the ``?backend`` query parameter.

    Returns:
        The ``StorageBackend`` instance matching *backend*.

    Raises:
        HTTPException: 400 if the backend is not registered.

    """
    return get(backend)
