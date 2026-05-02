from typing import Annotated

from fastapi import Depends, Query, Request

from strata.plugins.protocols import StorageBackend
from strata.plugins.registry import FileHandlerRegistry, PluginRegistry, StorageRegistry


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


def storage_backend_dep(
    storage_registry: Annotated[StorageRegistry, Depends(storage_registry_dep)],
    backend: Annotated[str, Query(description="Backend id")],
) -> StorageBackend:
    return storage_registry.get(backend_id=backend)


StorageRegistryDep = Annotated[StorageRegistry, Depends(storage_registry_dep)]
FileHandlerRegistryDep = Annotated[FileHandlerRegistry, Depends(file_handlers_registry_dep)]
