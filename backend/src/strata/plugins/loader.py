"""Plugin discovery and lifecycle management for Strata.

Plugins are discovered via the ``strata.plugins`` entry point group defined
in :pep:`517` / :pep:`660` ``pyproject.toml`` files.  Only plugins whose
entry point *name* appears in :attr:`~strata.config.Settings.ENABLED_PLUGINS`
are loaded.

Startup sequence (per plugin)
------------------------------
1. Load the entry point to obtain the :class:`~strata.plugins.base.BackendPlugin`
   instance.
2. Call :meth:`~strata.plugins.base.BackendPlugin.register` — synchronous,
   contributes capabilities to the :class:`~strata.plugins.registry.PluginRegistry`.
3. Call :meth:`~strata.plugins.base.BackendPlugin.on_startup` — async
   initialisation (connection pools, caches, etc.).

Shutdown sequence
-----------------
:func:`shutdown_all` calls :meth:`~strata.plugins.base.BackendPlugin.on_shutdown`
on every loaded plugin in *reverse* load order, mirroring the startup sequence.

Declaring a plugin (in the plugin package's ``pyproject.toml``)::

    [project.entry-points."strata.plugins"]
    image_preview = "strata_image_preview:plugin"

Enabling a plugin (in Strata's ``.env`` or environment)::

    STRATA_ENABLED_PLUGINS=image_preview,collabora
"""

import logging
from importlib.metadata import EntryPoint, entry_points

from strata.config import settings
from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry

L = logging.getLogger(__name__)


def _discover_entry_points(enabled: list[str]) -> list[EntryPoint]:
    """Return entry points for enabled plugins in the order they are listed.

    Args:
        enabled: Ordered list of plugin ids to load, e.g.
            ``["image_preview", "collabora"]``.

    Returns:
        The matching :class:`importlib.metadata.EntryPoint` objects in the
        same order as *enabled*, skipping any ids not found in the installed
        entry point group.
    """
    all_eps: dict[str, EntryPoint] = {
        ep.name: ep for ep in entry_points(group=settings.ENTRY_POINT_GROUP)
    }
    L.warning("Discovered plugins: %s", ", ".join(all_eps))
    found: list[EntryPoint] = []
    for plugin_id in enabled:
        if plugin_id in all_eps:
            found.append(all_eps[plugin_id])
        else:
            L.warning(
                "Enabled plugin %r not found in entry point group %r — skipping.",
                plugin_id,
                settings.ENTRY_POINT_GROUP,
            )
    return found


def _load_entry_point(ep: EntryPoint) -> BackendPlugin | None:
    """Load one entry point and return the plugin instance.

    Args:
        ep: The entry point to load.

    Returns:
        The :class:`~strata.plugins.base.BackendPlugin` instance, or ``None``
        if loading fails or the entry point does not point to a valid instance.
    """
    try:
        obj = ep.load()
    except Exception:
        L.exception("Failed to load entry point %r — skipping.", ep.name)
        return None

    if not isinstance(obj, BackendPlugin):
        L.error(
            "Entry point %r resolved to %r, expected a BackendPlugin instance — skipping.",
            ep.name,
            type(obj).__name__,
        )
        return None

    return obj


class PluginLoader:
    """Plugin loader."""

    def __init__(self) -> None:
        self._loaded: list[BackendPlugin] = []

    async def load_and_register(
        self,
        registry: PluginRegistry,
        enabled: list[str],
    ):
        """Discover, register, and start all enabled plugins.

        This function should be called exactly once during the FastAPI ``startup``
        event.  It populates the ``_loaded`` list consumed by :meth:`get_loaded_plugins`.

        Args:
            registry: The application-wide
                :class:`~strata.plugins.registry.PluginRegistry` to populate.
            enabled: Ordered list of plugin ids to load, sourced from
                :attr:`~strata.config.Settings.ENABLED_PLUGINS`.

        Returns:
            The list of successfully loaded and started
            :class:`~strata.plugins.base.BackendPlugin` instances in load order.
        """
        self._loaded.clear()

        for ep in _discover_entry_points(enabled):
            plugin = _load_entry_point(ep)
            if plugin is None:
                continue

            try:
                plugin.register(registry)
            except Exception:
                L.exception("Plugin %r raised an exception in register() — skipping.", plugin.id)
                continue

            try:
                await plugin.on_startup()
            except Exception:
                L.exception("Plugin %r raised an exception in on_startup() — skipping.", plugin.id)
                continue

            self._loaded.append(plugin)
            L.info("Loaded plugin %r (%s %s)", plugin.id, plugin.name, plugin.version)

    async def shutdown_all(self) -> None:
        """Call ``on_shutdown()`` on every loaded plugin in reverse load order.

        Errors in individual plugins are logged but do not interrupt the shutdown
        of remaining plugins.
        """
        for plugin in reversed(self._loaded):
            try:
                await plugin.on_shutdown()
            except Exception:
                L.exception("Plugin %r raised an exception in on_shutdown().", plugin.id)
        self._loaded.clear()

    def get_loaded_plugins(self) -> list[BackendPlugin]:
        """Return the list of successfully loaded plugins in load order.

        Returns:
            A snapshot of the loaded plugin list.  Empty before
            :meth:`load_and_register` has been called.
        """
        return list(self._loaded)
