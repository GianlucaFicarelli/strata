"""Plugin discovery and lifecycle management for Strata.

At startup, :func:`discover_and_register` scans the ``strata.plugins_enabled``
package, loads every sub-package that exposes a valid ``plugin`` attribute,
calls each plugin's :meth:`~strata.plugins.base.BackendPlugin.register`
method, and then calls :meth:`~strata.plugins.base.BackendPlugin.on_startup`.

At shutdown, :func:`shutdown_all` calls
:meth:`~strata.plugins.base.BackendPlugin.on_shutdown` on every loaded plugin
in reverse load order.

The list of loaded plugins is kept as module-level state so that
``GET /api/plugins`` can read it without carrying the list through the
application object.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from types import ModuleType

from strata.plugins.base import BackendPlugin
from strata.plugins.registry import PluginRegistry

log = logging.getLogger(__name__)

_PLUGINS_PACKAGE = "strata.plugins_enabled"

# Ordered list of successfully loaded plugins, populated by discover_and_register().
_loaded: list[BackendPlugin] = []


# ── Internal helpers ──────────────────────────────────────────────────────────


def _iter_plugin_modules(package_name: str) -> list[ModuleType]:
    """Import every sub-module of *package_name* and return those that loaded.

    Modules that raise an exception on import are skipped and logged as
    errors so that a single broken plugin does not prevent the rest from
    loading.

    Args:
        package_name: Fully-qualified dotted name of the plugins package,
            e.g. ``"strata.plugins_enabled"``.

    Returns:
        A list of successfully imported ``ModuleType`` objects.
    """
    try:
        pkg = importlib.import_module(package_name)
    except ModuleNotFoundError:
        log.warning("Plugin package %r not found — no plugins loaded.", package_name)
        return []

    modules: list[ModuleType] = []
    for _finder, name, _is_pkg in pkgutil.iter_modules(pkg.__path__):
        full_name = f"{package_name}.{name}"
        try:
            modules.append(importlib.import_module(full_name))
        except Exception:  # noqa: BLE001
            log.exception("Failed to import plugin module %r — skipping.", full_name)

    return modules


def _extract_plugin(module: ModuleType) -> BackendPlugin | None:
    """Return the ``plugin`` singleton from *module*, or ``None`` if absent.

    A module is considered a valid plugin module if it exposes a top-level
    attribute named ``plugin`` that is an instance of :class:`BackendPlugin`.

    Args:
        module: An already-imported module to inspect.

    Returns:
        The :class:`BackendPlugin` instance, or ``None`` if the module does
        not export a valid ``plugin`` attribute.
    """
    candidate = getattr(module, "plugin", None)
    if isinstance(candidate, BackendPlugin):
        return candidate
    log.debug(
        "Module %r has no valid `plugin` attribute — skipping.",
        module.__name__,
    )
    return None


# ── Public API ────────────────────────────────────────────────────────────────


async def discover_and_register(registry: PluginRegistry) -> list[BackendPlugin]:
    """Discover plugins, register their capabilities, and call their startup hooks.

    This function should be called once during the FastAPI ``startup`` event.
    It populates the module-level ``_loaded`` list, which is read by
    :func:`get_loaded_plugins`.

    The loading sequence for each plugin is:

    1. Import the plugin module.
    2. Extract the ``plugin`` singleton.
    3. Call ``plugin.register(registry)`` — synchronous, contributes capabilities.
    4. Call ``await plugin.on_startup()`` — asynchronous initialisation.

    Args:
        registry: The application-wide
            :class:`~strata.plugins.registry.PluginRegistry` to populate.

    Returns:
        The list of successfully loaded :class:`~strata.plugins.base.BackendPlugin`
        instances in load order.
    """
    global _loaded  # noqa: PLW0603
    _loaded = []

    for module in _iter_plugin_modules(_PLUGINS_PACKAGE):
        plugin = _extract_plugin(module)
        if plugin is None:
            continue

        try:
            plugin.register(registry)
        except Exception:  # noqa: BLE001
            log.exception(
                "Plugin %r raised an exception in register() — skipping.",
                plugin.id,
            )
            continue

        try:
            await plugin.on_startup()
        except Exception:  # noqa: BLE001
            log.exception(
                "Plugin %r raised an exception in on_startup() — skipping.",
                plugin.id,
            )
            continue

        _loaded.append(plugin)
        log.info("Loaded plugin: %r (%s %s)", plugin.id, plugin.name, plugin.version)

    return _loaded


async def shutdown_all() -> None:
    """Call ``on_shutdown()`` on every loaded plugin in reverse load order.

    Errors in individual plugins are logged but do not prevent the remaining
    plugins from shutting down.
    """
    for plugin in reversed(_loaded):
        try:
            await plugin.on_shutdown()
        except Exception:  # noqa: BLE001
            log.exception("Plugin %r raised an exception in on_shutdown().", plugin.id)


def get_loaded_plugins() -> list[BackendPlugin]:
    """Return the list of successfully loaded plugins.

    Returns:
        A snapshot of the loaded plugin list in load order.  The list is
        populated by :func:`discover_and_register` and is empty before that
        function has been called.
    """
    return list(_loaded)