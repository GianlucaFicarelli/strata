"""Plugin registry — the collection of all extension points in Strata.

A single :class:`PluginRegistry` instance is created at application startup
and passed to every plugin's :meth:`~strata.plugins.base.BackendPlugin.register`
method.  Plugins call the typed ``add`` methods on each sub-registry to
contribute their capabilities.

The application then reads from these registries when wiring up routes,
resolving ``?backend=`` parameters, serving frontend assets, and so on.

Example::

    # Inside a plugin's register() method:
    def register(self, registry: PluginRegistry) -> None:
        registry.storage.add(MyStorageBackend())
        registry.routes.add(my_api_router)
        registry.file_handlers.add(MyFileHandler())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException

from strata.plugins.protocols import FileHandler, RouteProvider, StorageBackend

if TYPE_CHECKING:
    from fastapi import APIRouter

log = logging.getLogger(__name__)


# ── Individual registries ─────────────────────────────────────────────────────


class StorageRegistry:
    """Registry of available storage backends.

    The ``local`` backend is pre-registered at construction time.  Plugins
    add further backends via :meth:`add`.  The registry is queried by the
    ``backend_dep`` FastAPI dependency to resolve ``?backend=<id>`` on
    every file endpoint.
    """

    def __init__(self) -> None:
        self._backends: dict[str, StorageBackend] = {}

    def add(self, backend: StorageBackend) -> None:
        """Register a storage backend.

        If a backend with the same :attr:`~StorageBackend.id` already exists
        it will be replaced and a warning will be logged.

        Args:
            backend: A :class:`~strata.plugins.protocols.StorageBackend`
                implementation to register.
        """
        if backend.id in self._backends:
            log.warning("Replacing already-registered storage backend %r", backend.id)
        self._backends[backend.id] = backend
        log.info("Registered storage backend: %r (%s)", backend.id, backend.name)

    def get(self, backend_id: str) -> StorageBackend:
        """Look up a backend by its :attr:`~StorageBackend.id`.

        Args:
            backend_id: The identifier to look up.

        Returns:
            The matching :class:`~strata.plugins.protocols.StorageBackend`.

        Raises:
            HTTPException: 400 if *backend_id* is not registered.
        """
        try:
            return self._backends[backend_id]
        except KeyError:
            available = sorted(self._backends)
            raise HTTPException(
                status_code=400,
                detail=f"Unknown backend {backend_id!r}. Available: {available}",
            ) from None

    def all(self) -> list[StorageBackend]:
        """Return every registered backend in registration order.

        Returns:
            A list of :class:`~strata.plugins.protocols.StorageBackend` instances.
        """
        return list(self._backends.values())


class RouteRegistry:
    """Registry of FastAPI routers contributed by plugins.

    Routers are collected during the plugin registration phase and then
    mounted onto the FastAPI application in a single pass by the startup
    handler.
    """

    def __init__(self) -> None:
        self._routers: list[RouteProvider] = []

    def add(self, provider: RouteProvider) -> None:
        """Register a route provider.

        Args:
            provider: A :class:`~strata.plugins.protocols.RouteProvider`
                whose :meth:`~RouteProvider.get_router` will be mounted at
                startup.
        """
        self._routers.append(provider)
        log.info("Registered route provider: %r", type(provider).__name__)

    def all(self) -> list[APIRouter]:
        """Return all registered routers, ready to be mounted.

        Returns:
            A list of ``fastapi.APIRouter`` instances.
        """
        return [p.get_router() for p in self._routers]


class FileHandlerRegistry:
    """Registry of frontend file handlers.

    Each :class:`~strata.plugins.protocols.FileHandler` declares which file
    extensions it covers and the URL of its JavaScript ES module.  The
    frontend shell loads these modules dynamically and uses the ``handles``
    lists to route file-open events to the correct viewer or editor.
    """

    def __init__(self) -> None:
        self._handlers: list[FileHandler] = []

    def add(self, handler: FileHandler) -> None:
        """Register a file handler.

        Args:
            handler: A :class:`~strata.plugins.protocols.FileHandler`
                implementation to register.
        """
        self._handlers.append(handler)
        log.info(
            "Registered file handler %r for extensions: %s",
            type(handler).__name__,
            handler.handles,
        )

    def all(self) -> list[FileHandler]:
        """Return every registered file handler.

        Returns:
            A list of :class:`~strata.plugins.protocols.FileHandler` instances.
        """
        return list(self._handlers)

    def for_extension(self, ext: str) -> FileHandler | None:
        """Find the first handler that covers a given file extension.

        Args:
            ext: Lower-cased extension including the leading dot,
                e.g. ``".docx"``.

        Returns:
            The first matching :class:`~strata.plugins.protocols.FileHandler`,
            or ``None`` if no handler covers *ext*.
        """
        return next((h for h in self._handlers if ext in h.handles), None)


# ── Composite registry ────────────────────────────────────────────────────────


@dataclass
class PluginRegistry:
    """Composite registry passed to every plugin's ``register()`` method.

    Each field is a typed sub-registry for one category of extension point.
    Plugins call the appropriate ``add`` methods to contribute their
    capabilities.  The application reads from these registries when wiring
    routes, resolving storage backends, and building the frontend plugin
    manifest.

    Attributes:
        storage: Registry of :class:`~strata.plugins.protocols.StorageBackend`
            implementations.
        routes: Registry of :class:`~strata.plugins.protocols.RouteProvider`
            implementations.
        file_handlers: Registry of :class:`~strata.plugins.protocols.FileHandler`
            implementations.
    """

    storage: StorageRegistry = field(default_factory=StorageRegistry)
    routes: RouteRegistry = field(default_factory=RouteRegistry)
    file_handlers: FileHandlerRegistry = field(default_factory=FileHandlerRegistry)