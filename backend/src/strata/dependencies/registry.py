"""Registry dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from strata.plugins.registry import (
    AuthRegistry,
    DbRegistry,
    FileHandlerRegistry,
    PluginRegistry,
    RouteRegistry,
    SearchRegistry,
    StorageRegistry,
    StorageTemplateRegistry,
    ThumbRegistry,
)


def plugin_registry_dep(request: Request) -> PluginRegistry:
    return request.state.plugin_registry


PluginRegistryDep = Annotated[PluginRegistry, Depends(plugin_registry_dep)]


def storage_registry_dep(plugin_registry: PluginRegistryDep) -> StorageRegistry:
    return plugin_registry.storage


def storage_template_registry_dep(
    plugin_registry: PluginRegistryDep,
) -> StorageTemplateRegistry:
    return plugin_registry.storage_templates


def route_registry_dep(plugin_registry: PluginRegistryDep) -> RouteRegistry:
    return plugin_registry.routes


def file_handlers_registry_dep(plugin_registry: PluginRegistryDep) -> FileHandlerRegistry:
    return plugin_registry.file_handlers


def auth_registry_dep(plugin_registry: PluginRegistryDep) -> AuthRegistry:
    return plugin_registry.auth


def search_registry_dep(plugin_registry: PluginRegistryDep) -> SearchRegistry:
    return plugin_registry.search


def thumbs_registry_dep(plugin_registry: PluginRegistryDep) -> ThumbRegistry:
    return plugin_registry.thumbs


def db_registry_dep(plugin_registry: PluginRegistryDep) -> DbRegistry:
    return plugin_registry.db


StorageRegistryDep = Annotated[StorageRegistry, Depends(storage_registry_dep)]
StorageTemplateRegistryDep = Annotated[
    StorageTemplateRegistry, Depends(storage_template_registry_dep)
]
RouteRegistryDep = Annotated[RouteRegistry, Depends(route_registry_dep)]
FileHandlerRegistryDep = Annotated[FileHandlerRegistry, Depends(file_handlers_registry_dep)]
AuthRegistryDep = Annotated[AuthRegistry, Depends(auth_registry_dep)]
SearchRegistryDep = Annotated[SearchRegistry, Depends(search_registry_dep)]
ThumbRegistryDep = Annotated[ThumbRegistry, Depends(thumbs_registry_dep)]
DBRegistryDep = Annotated[DbRegistry, Depends(db_registry_dep)]
