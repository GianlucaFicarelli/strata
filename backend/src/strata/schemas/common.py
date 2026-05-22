"""Common schemas."""

from pydantic import BaseModel


class PluginMeta(BaseModel):
    """Plugin metadata."""

    id: str
    name: str
    version: str
    description: str


class StorageMeta(BaseModel):
    """Minimal backend descriptor used by the StorageBackend protocol.

    Returned by ``StorageBackend.describe()``.  Not used directly as an API
    response schema — see ``ReadyBackendMeta`` in ``schemas/storage.py`` for
    the richer shape returned to clients.
    """

    id: str
    name: str
