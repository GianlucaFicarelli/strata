"""Plugin discovery and loading for Strata."""

import importlib
import pkgutil

from strata.plugins.base import BackendPlugin

_plugins: list[BackendPlugin] = []


def discover_plugins(package_name: str = "plugins_enabled") -> list[BackendPlugin]:
    """Scan a package and load every module that exports a valid plugin.

    A module is considered a plugin if it exposes a top-level ``plugin``
    attribute that is an instance of ``BackendPlugin``.

    Args:
        package_name: Dotted import path of the package to scan.
            Defaults to ``"plugins_enabled"``.

    Returns:
        The list of successfully loaded ``BackendPlugin`` instances.
        Modules that fail to import or lack a valid ``plugin`` export
        are skipped and logged to stdout.

    """
    global _plugins  # noqa: PLW0603
    _plugins = []

    try:
        pkg = importlib.import_module(package_name)
    except ModuleNotFoundError:
        print(f"[plugin-loader] Package '{package_name}' not found — no plugins loaded.")
        return _plugins

    for _finder, name, _is_pkg in pkgutil.iter_modules(pkg.__path__):
        full_name = f"{package_name}.{name}"
        try:
            mod = importlib.import_module(full_name)
            if hasattr(mod, "plugin") and isinstance(mod.plugin, BackendPlugin):
                _plugins.append(mod.plugin)
                print(f"[plugin-loader] Loaded plugin: {mod.plugin.id} ({mod.plugin.name})")
            else:
                print(f"[plugin-loader] Skipped {full_name}: no valid `plugin` export.")
        except Exception as exc:  # noqa: BLE001
            print(f"[plugin-loader] Failed to load {full_name}: {exc}")

    return _plugins


def get_plugins() -> list[BackendPlugin]:
    """Return all currently loaded plugins.

    Returns:
        The list of ``BackendPlugin`` instances loaded by the most
        recent call to ``discover_plugins``.

    """
    return _plugins


def get_plugin(plugin_id: str) -> BackendPlugin | None:
    """Look up a loaded plugin by its id.

    Args:
        plugin_id: The ``id`` attribute of the desired plugin.

    Returns:
        The matching ``BackendPlugin``, or ``None`` if not found.

    """
    return next((p for p in _plugins if p.id == plugin_id), None)
