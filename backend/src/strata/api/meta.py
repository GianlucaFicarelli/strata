from fastapi import APIRouter, Request

from strata.dependencies.registry import StorageRegistryDep
from strata.plugins.loader import PluginLoader
from strata.schemas.common import PluginMeta, StorageMeta

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/plugins")
def list_plugins(request: Request) -> list[PluginMeta]:
    """Return metadata for every loaded plugin.

    The frontend uses this to dynamically import each plugin's JS module
    and to know which file extensions each plugin handles.

    Returns:
        A list of dicts produced by ``BackendPlugin.describe()``.

    """
    plugin_loader: PluginLoader = request.state.plugin_loader
    return [p.describe() for p in plugin_loader.get_loaded_plugins()]


@router.get("/backends")
def list_backends(storage_registry: StorageRegistryDep) -> list[StorageMeta]:
    """Return metadata for every registered storage backend.

    The frontend uses this to populate the backend picker dropdown.

    Returns:
        A list of dicts, one per registered ``StorageBackend``.

    """
    return [b.describe() for b in storage_registry.all()]
