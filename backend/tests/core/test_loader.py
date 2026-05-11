"""Unit tests for strata.plugins.loader.

Tests use monkeypatch to replace ``entry_points`` and ``_load_entry_point``
so no real packages need to be installed.
"""

import logging

from strata.plugins.base import BackendPlugin
from strata.plugins.loader import PluginLoader, _discover_entry_points, _load_entry_point
from strata.plugins.registry import PluginRegistry

# ── Stub plugin ───────────────────────────────────────────────────────────────


class _GoodPlugin(BackendPlugin):
    id = "good"
    name = "Good Plugin"
    version = "1.0.0"
    description = "A test plugin."

    registered: bool = False
    started: bool = False
    stopped: bool = False

    def register(self, registry: PluginRegistry) -> None:
        _GoodPlugin.registered = True

    async def on_startup(self) -> None:
        _GoodPlugin.started = True

    async def on_shutdown(self) -> None:
        _GoodPlugin.stopped = True


class _BrokenRegisterPlugin(BackendPlugin):
    id = "broken_reg"
    name = "Broken Register"
    version = "1.0.0"
    description = ""

    def register(self, registry: PluginRegistry) -> None:
        raise RuntimeError("boom in register")


class _BrokenStartupPlugin(BackendPlugin):
    id = "broken_startup"
    name = "Broken Startup"
    version = "1.0.0"
    description = ""

    async def on_startup(self) -> None:
        raise RuntimeError("boom in startup")


# ── _discover_entry_points ────────────────────────────────────────────────────


class _FakeEP:
    """Minimal EntryPoint stub — EntryPoint is immutable in Python 3.12."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group = "strata.plugins"
        self.value = f"fake_{name}:plugin"
        self._loader = None

    def load(self):
        if self._loader is not None:
            return self._loader()
        raise ImportError(f"No loader set for {self.name}")


def _make_ep(name: str) -> _FakeEP:
    return _FakeEP(name)


def test_discover_entry_points_returns_in_enabled_order(monkeypatch):
    ep_a = _make_ep("alpha")
    ep_b = _make_ep("beta")

    monkeypatch.setattr(
        "strata.plugins.loader.entry_points",
        lambda group: [ep_b, ep_a],
    )

    result = _discover_entry_points(["alpha", "beta"])
    assert [ep.name for ep in result] == ["alpha", "beta"]


def test_discover_entry_points_skips_unknown(monkeypatch, caplog):
    monkeypatch.setattr(
        "strata.plugins.loader.entry_points",
        lambda group: [_make_ep("known")],
    )
    with caplog.at_level(logging.WARNING, logger="strata.plugins.loader"):
        result = _discover_entry_points(["unknown", "known"])
    assert len(result) == 1
    assert result[0].name == "known"
    assert "unknown" in caplog.text


def test_discover_entry_points_empty_enabled(monkeypatch):
    monkeypatch.setattr(
        "strata.plugins.loader.entry_points",
        lambda group: [_make_ep("whatever")],
    )
    assert _discover_entry_points([]) == []


# ── _load_entry_point ─────────────────────────────────────────────────────────


def test_load_entry_point_returns_plugin():
    plugin = _GoodPlugin()
    ep = _make_ep("good")
    ep._loader = lambda: plugin
    result = _load_entry_point(ep)
    assert result is plugin


def test_load_entry_point_returns_none_on_exception(caplog):
    ep = _make_ep("bad")
    ep._loader = lambda: (_ for _ in ()).throw(ImportError("oops"))
    with caplog.at_level(logging.ERROR, logger="strata.plugins.loader"):
        result = _load_entry_point(ep)
    assert result is None


def test_load_entry_point_returns_none_for_non_plugin(caplog):
    ep = _make_ep("notplugin")
    ep._loader = lambda: "not_a_plugin"
    with caplog.at_level(logging.ERROR, logger="strata.plugins.loader"):
        result = _load_entry_point(ep)
    assert result is None


# ── PluginLoader ──────────────────────────────────────────────────────────────


async def test_loader_loads_good_plugin(monkeypatch):
    plugin = _GoodPlugin()
    _GoodPlugin.registered = False
    _GoodPlugin.started = False

    monkeypatch.setattr(
        "strata.plugins.loader._discover_entry_points",
        lambda enabled: [_make_ep("good")],
    )
    monkeypatch.setattr(
        "strata.plugins.loader._load_entry_point",
        lambda ep: plugin,
    )

    loader = PluginLoader()
    registry = PluginRegistry()
    await loader.load_and_register(registry=registry, enabled=["good"])

    assert _GoodPlugin.registered
    assert _GoodPlugin.started
    assert loader.get_loaded_plugins() == [plugin]


async def test_loader_skips_plugin_with_bad_register(monkeypatch, caplog):
    bad = _BrokenRegisterPlugin()

    monkeypatch.setattr(
        "strata.plugins.loader._discover_entry_points",
        lambda enabled: [_make_ep("broken_reg")],
    )
    monkeypatch.setattr(
        "strata.plugins.loader._load_entry_point",
        lambda ep: bad,
    )

    loader = PluginLoader()
    with caplog.at_level(logging.ERROR, logger="strata.plugins.loader"):
        await loader.load_and_register(registry=PluginRegistry(), enabled=["broken_reg"])

    assert loader.get_loaded_plugins() == []


async def test_loader_skips_plugin_with_bad_startup(monkeypatch, caplog):
    bad = _BrokenStartupPlugin()

    monkeypatch.setattr(
        "strata.plugins.loader._discover_entry_points",
        lambda enabled: [_make_ep("broken_startup")],
    )
    monkeypatch.setattr(
        "strata.plugins.loader._load_entry_point",
        lambda ep: bad,
    )

    loader = PluginLoader()
    with caplog.at_level(logging.ERROR, logger="strata.plugins.loader"):
        await loader.load_and_register(registry=PluginRegistry(), enabled=["broken_startup"])

    assert loader.get_loaded_plugins() == []


async def test_loader_shutdown_calls_on_shutdown_in_reverse(monkeypatch):
    order: list[str] = []

    class _A(BackendPlugin):
        id, name, version, description = "a", "A", "1.0.0", ""

        async def on_shutdown(self):
            order.append("a")

    class _B(BackendPlugin):
        id, name, version, description = "b", "B", "1.0.0", ""

        async def on_shutdown(self):
            order.append("b")

    a, b = _A(), _B()
    eps = [_make_ep("a"), _make_ep("b")]

    monkeypatch.setattr(
        "strata.plugins.loader._discover_entry_points",
        lambda enabled: eps,
    )
    monkeypatch.setattr(
        "strata.plugins.loader._load_entry_point",
        lambda ep: a if ep.name == "a" else b,
    )

    loader = PluginLoader()
    await loader.load_and_register(registry=PluginRegistry(), enabled=["a", "b"])
    await loader.shutdown_all()

    assert order == ["b", "a"]


async def test_loader_get_loaded_plugins_empty_before_load():
    loader = PluginLoader()
    assert loader.get_loaded_plugins() == []
