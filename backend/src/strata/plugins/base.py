"""Base class for all Strata plugins."""

from typing import TYPE_CHECKING

from strata.schemas.common import PluginMeta

if TYPE_CHECKING:
    from strata.plugins.registry import PluginRegistry


class BackendPlugin:
    """Base class for all Strata plugins.

    A plugin is a Python package that:

    1. Declares itself via a ``strata.plugins`` entry point in its
       ``pyproject.toml``.
    2. Exposes a module-level ``plugin`` attribute that is an instance of a
       ``BackendPlugin`` subclass.
    3. Implements :meth:`register` to contribute capabilities to the
       application by calling the typed ``add`` methods on the
       :class:`~strata.plugins.registry.PluginRegistry`.

    The base class provides no-op implementations of all lifecycle methods so
    that subclasses only need to override what they actually use.

    Attributes:
        id: Unique snake_case identifier, e.g. ``"image_preview"``.  Must be
            unique across all installed plugins and must match the entry point
            name declared in ``pyproject.toml``.
        name: Human-readable display name, e.g. ``"Image Preview"``.
        version: SemVer string, e.g. ``"0.1.0"``.
        description: One-line description shown in the admin plugin list.

    Example::

        # src/strata_myplugin/__init__.py
        from strata.plugins.base import BackendPlugin
        from strata.plugins.registry import PluginRegistry

        class MyPlugin(BackendPlugin):
            id = "myplugin"
            name = "My Plugin"
            version = "0.1.0"
            description = "Does something useful."

            def register(self, registry: PluginRegistry) -> None:
                registry.storage.add(MyStorageBackend())
                registry.routes.add(MyRouteProvider())

        plugin = MyPlugin()

        # pyproject.toml of strata-myplugin:
        # [project.entry-points."strata.plugins"]
        # myplugin = "strata_myplugin:plugin"
    """

    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    description: str = ""

    def register(self, registry: PluginRegistry) -> None:
        """Contribute this plugin's capabilities to the application.

        Called once at startup, after the plugin is discovered and before
        :meth:`on_startup`.  Override this method and call the typed ``add``
        methods on the appropriate sub-registries:

        - ``registry.storage.add(...)`` for a storage backend
        - ``registry.routes.add(...)`` for extra API routes
        - ``registry.file_handlers.add(...)`` for a frontend viewer/editor
        - ``registry.auth.add(...)`` for an authentication provider
        - ``registry.search.add(...)`` for a search provider
        - ``registry.thumbs.add(...)`` for a thumbnail generator

        Multiple contributions of the same or different types are allowed.

        Args:
            registry: The application-wide plugin registry.
        """

    async def on_startup(self) -> None:
        """Called once at startup, after :meth:`register`.

        Use for async initialisation such as opening connection pools or
        warming caches.  The default implementation does nothing.
        """

    async def on_shutdown(self) -> None:
        """Called once when the application is shutting down.

        Use to release resources acquired in :meth:`on_startup`.  The default
        implementation does nothing.
        """

    def describe(self) -> PluginMeta:
        """Return a JSON-serialisable summary of this plugin.

        Used by ``GET /api/plugins`` to build the manifest sent to the
        frontend shell.

        Returns:
            A PluginMeta instance.
        """
        return PluginMeta(
            id=self.id,
            name=self.name,
            version=self.version,
            description=self.description,
        )
