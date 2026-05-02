"""Base class for all Strata plugins.

A plugin is a Python package placed inside ``strata/plugins_enabled/`` that
exposes a module-level ``plugin`` attribute — an instance of a
:class:`BackendPlugin` subclass.

The plugin's :meth:`BackendPlugin.register` method receives a
:class:`~strata.plugins.registry.PluginRegistry` at startup and contributes
to whichever extension points it supports by calling the typed ``add``
methods on the appropriate sub-registries.

Minimal example::

    # strata/plugins_enabled/hello/__init__.py
    from strata.plugins.base import BackendPlugin
    from strata.plugins.registry import PluginRegistry

    class HelloPlugin(BackendPlugin):
        id = "hello"
        name = "Hello"

        def register(self, registry: PluginRegistry) -> None:
            pass   # nothing to contribute

    plugin = HelloPlugin()

A plugin that contributes a storage backend *and* custom API routes::

    from fastapi import APIRouter
    from strata.plugins.base import BackendPlugin
    from strata.plugins.protocols import RouteProvider, StorageBackend
    from strata.plugins.registry import PluginRegistry

    router = APIRouter(prefix="/api/plugins/myplugin")

    class MyStorage: ...          # implements StorageBackend protocol
    class MyRoutes:               # implements RouteProvider protocol
        def get_router(self) -> APIRouter:
            return router

    class MyPlugin(BackendPlugin):
        id = "myplugin"
        name = "My Plugin"

        def register(self, registry: PluginRegistry) -> None:
            registry.storage.add(MyStorage())
            registry.routes.add(MyRoutes())

    plugin = MyPlugin()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strata.plugins.registry import PluginRegistry


class BackendPlugin:
    """Base class for all Strata plugins.

    Subclass this and implement :meth:`register` to contribute capabilities
    to the application.  Each plugin package must expose a module-level
    ``plugin`` attribute that is an instance of a ``BackendPlugin`` subclass;
    the plugin loader uses this attribute to discover plugins.

    Attributes:
        id: Unique snake_case identifier for this plugin, e.g.
            ``"image_preview"``.  Must be unique across all installed plugins.
        name: Human-readable display name, e.g. ``"Image Preview"``.
        version: SemVer string, e.g. ``"0.1.0"``.
        description: One-line description shown in the admin plugin list.
    """

    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    description: str = ""

    def register(self, registry: PluginRegistry) -> None:
        """Contribute this plugin's capabilities to the application.

        Called once at startup, after the plugin is discovered and before
        :meth:`on_startup`.  Implementations should call the typed ``add``
        methods on the appropriate sub-registries:

        - ``registry.storage.add(...)`` — to register a storage backend
        - ``registry.routes.add(...)`` — to mount extra API routes
        - ``registry.file_handlers.add(...)`` — to register a frontend viewer

        Multiple contributions of the same or different types are allowed in
        a single ``register`` call.

        Args:
            registry: The application-wide
                :class:`~strata.plugins.registry.PluginRegistry` instance.
        """

    async def on_startup(self) -> None:
        """Called once at application startup, after :meth:`register`.

        Use this for asynchronous initialisation that cannot be done at
        import time, such as opening a connection pool or pre-warming a cache.
        The default implementation does nothing.
        """

    async def on_shutdown(self) -> None:
        """Called once when the application is shutting down.

        Use this to release resources acquired in :meth:`on_startup`, such
        as closing connection pools.  The default implementation does nothing.
        """

    def describe(self) -> dict[str, object]:
        """Return a JSON-serialisable summary of this plugin.

        Called by ``GET /api/plugins`` to build the plugin manifest sent to
        the frontend shell.  The manifest tells the shell which JavaScript
        modules to load and which file extensions each handler covers.

        Returns:
            A dict with ``id``, ``name``, ``version``, ``description``,
            ``file_handlers``, and ``routes`` keys.  Override to add
            plugin-specific metadata.
        """
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }