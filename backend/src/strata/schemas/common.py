"""Common schemas."""

from pydantic import BaseModel


class PluginMeta(BaseModel):
    """Plugin metadata."""

    id: str
    name: str
    version: str
    description: str


class StorageMeta(BaseModel):
    """Storage metadata."""

    id: str
    name: str
