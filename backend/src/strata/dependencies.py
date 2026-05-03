"""FastAPI dependency functions for Strata.

All application-wide ``Depends`` helpers live here.  Plugin routes should
import from this module rather than reaching into ``request.state`` directly.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.db import session_scope
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


def session_factory_dep(request: Request) -> async_sessionmaker[AsyncSession]:
    """Extract the session factory from ``request.state``."""
    return request.state.db_session_factory


async def db_session_dep(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(session_factory_dep)],
) -> AsyncGenerator[AsyncSession]:
    """Yield one :class:`~sqlalchemy.ext.asyncio.AsyncSession` per request.

    Commits on success, rolls back on any unhandled exception.
    """
    async with session_scope(session_factory) as session:
        yield session


StorageRegistryDep = Annotated[StorageRegistry, Depends(storage_registry_dep)]
FileHandlerRegistryDep = Annotated[FileHandlerRegistry, Depends(file_handlers_registry_dep)]
StorageBackendDep = Annotated[StorageBackend, Depends(storage_backend_dep)]
AsyncSessionDep = Annotated[AsyncSession, Depends(db_session_dep)]
