"""Common schemas."""

from pydantic import BaseModel


class PluginMeta(BaseModel):
    """Plugin metadata."""

    id: str
    name: str
    version: str
    description: str


class StorageMeta(BaseModel):
    """Storage backend metadata returned by GET /api/backends."""

    id: str
    name: str
    plugin_id: str | None = None
    instance_id: str | None = None
