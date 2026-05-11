"""Unit tests for strata.plugins.registry.

Tests cover every sub-registry's add / get / all methods and the
composite PluginRegistry dataclass.  All objects are lightweight stubs —
no database, no HTTP.
"""

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter, HTTPException
from sqlalchemy import MetaData

from strata.plugins.protocols import AuthUser, FileEntry
from strata.plugins.registry import (
    AuthRegistry,
    DbRegistry,
    FileHandlerRegistry,
    PluginRegistry,
    RouteRegistry,
    SearchRegistry,
    StorageRegistry,
    ThumbRegistry,
)

# ── Minimal stubs ─────────────────────────────────────────────────────────────


class _Storage:
    def __init__(self, id: str, name: str = "Test") -> None:  # noqa: A002
        self.id = id
        self.name = name

    async def list(self, path: str) -> list[FileEntry]:
        return []

    async def read(self, path: str) -> AsyncIterator[bytes]: ...
    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None: ...
    async def delete(self, path: str) -> None: ...
    async def mkdir(self, path: str) -> None: ...
    async def move(self, src: str, dst: str) -> None: ...
    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}


class _FileHandler:
    def __init__(self, exts: list[str]) -> None:
        self.handles = exts
        self.frontend_module = "/fake/module.js"


class _RouteProvider:
    def get_router(self) -> APIRouter:
        return APIRouter()


class _AuthProvider:
    def __init__(self, id: str = "test_auth") -> None:  # noqa: A002
        self.id = id
        self.name = "Test Auth"

    async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
        if credentials.get("username") == "alice":
            return AuthUser(id="uid-1", username="alice")
        return None


class _SearchProvider:
    def __init__(self, backend_id: str = "local") -> None:
        self.backend_id = backend_id

    async def search(self, query: str, path: str = "/", *, limit: int = 50):
        return []

    async def index(self, entry: FileEntry, content: AsyncIterator[bytes]) -> None: ...
    async def deindex(self, path: str) -> None: ...


class _ThumbProvider:
    def __init__(self, mime_prefix: str = "image/") -> None:
        self._prefix = mime_prefix

    def can_handle(self, mime: str) -> bool:
        return mime.startswith(self._prefix)

    async def generate(
        self, stream: AsyncIterator[bytes], *, width: int = 256, height: int = 256
    ) -> bytes:
        return b"fake-thumb"


class _DbContributor:
    metadata: MetaData = MetaData()
    migrations_dir: Path = Path("/fake/migrations")


# ── StorageRegistry ───────────────────────────────────────────────────────────


def test_storage_add_and_get():
    reg = StorageRegistry()
    s = _Storage("s3")
    reg.add(s)
    assert reg.get("s3") is s


def test_storage_get_unknown_raises_400():
    reg = StorageRegistry()
    with pytest.raises(HTTPException) as exc_info:
        reg.get("nope")
    assert exc_info.value.status_code == 400


def test_storage_all_returns_in_order():
    reg = StorageRegistry()
    a, b = _Storage("a"), _Storage("b")
    reg.add(a)
    reg.add(b)
    assert reg.all() == [a, b]


def test_storage_replace_logs_warning(caplog):
    reg = StorageRegistry()
    reg.add(_Storage("dup"))
    with caplog.at_level(logging.WARNING, logger="strata.plugins.registry"):
        reg.add(_Storage("dup"))
    assert "Replacing" in caplog.text


# ── FileHandlerRegistry ───────────────────────────────────────────────────────


def test_file_handler_for_extension_found():
    reg = FileHandlerRegistry()
    h = _FileHandler([".png", ".jpg"])
    reg.add(h)
    assert reg.for_extension(".png") is h


def test_file_handler_for_extension_not_found():
    reg = FileHandlerRegistry()
    reg.add(_FileHandler([".png"]))
    assert reg.for_extension(".pdf") is None


def test_file_handler_first_match_wins():
    reg = FileHandlerRegistry()
    h1 = _FileHandler([".docx"])
    h2 = _FileHandler([".docx"])
    reg.add(h1)
    reg.add(h2)
    assert reg.for_extension(".docx") is h1


# ── RouteRegistry ─────────────────────────────────────────────────────────────


def test_route_registry_all_routers():
    reg = RouteRegistry()
    reg.add(_RouteProvider())
    reg.add(_RouteProvider())
    routers = reg.all_routers()
    assert len(routers) == 2
    assert all(isinstance(r, APIRouter) for r in routers)


# ── AuthRegistry ──────────────────────────────────────────────────────────────


async def test_auth_registry_returns_first_match():
    reg = AuthRegistry()
    reg.add(_AuthProvider())
    user = await reg.authenticate({"username": "alice", "password": "x"})
    assert user is not None
    assert user.username == "alice"


async def test_auth_registry_returns_none_when_no_match():
    reg = AuthRegistry()
    reg.add(_AuthProvider())
    result = await reg.authenticate({"username": "nobody"})
    assert result is None


async def test_auth_registry_tries_providers_in_order():
    calls: list[str] = []

    class Recorder(_AuthProvider):
        def __init__(self, id: str) -> None:  # noqa: A002
            super().__init__(id)
            self._my_id = id

        async def authenticate(self, credentials: dict[str, str]) -> AuthUser | None:
            calls.append(self._my_id)
            return None

    reg = AuthRegistry()
    reg.add(Recorder("first"))
    reg.add(Recorder("second"))
    await reg.authenticate({})
    assert calls == ["first", "second"]


# ── SearchRegistry ────────────────────────────────────────────────────────────


async def test_search_registry_returns_empty_for_unknown_backend():
    reg = SearchRegistry()
    results = await reg.search("local", "cats")
    assert results == []


async def test_search_registry_delegates_to_provider():
    class _FakeSearch(_SearchProvider):
        async def search(self, query: str, path: str = "/", *, limit: int = 50):
            return [query]  # echo the query as a stand-in

    reg = SearchRegistry()
    reg.add(_FakeSearch("local"))
    results = await reg.search("local", "kittens")
    assert results == ["kittens"]


# ── ThumbRegistry ─────────────────────────────────────────────────────────────


def test_thumb_registry_for_mime():
    reg = ThumbRegistry()
    reg.add(_ThumbProvider("image/"))
    assert reg.for_mime("image/png") is not None
    assert reg.for_mime("video/mp4") is None


async def test_thumb_registry_generate_returns_none_when_unhandled():
    async def _empty():
        yield b""

    reg = ThumbRegistry()
    result = await reg.generate("application/pdf", _empty())
    assert result is None


# ── DbRegistry ────────────────────────────────────────────────────────────────


def test_db_registry_preserves_insertion_order():
    reg = DbRegistry()
    a, b, c = _DbContributor(), _DbContributor(), _DbContributor()
    reg.add(a)
    reg.add(b)
    reg.add(c)
    assert reg.all() == [a, b, c]


# ── PluginRegistry composite ──────────────────────────────────────────────────


def test_plugin_registry_has_all_sub_registries():
    reg = PluginRegistry()
    assert isinstance(reg.storage, StorageRegistry)
    assert isinstance(reg.routes, RouteRegistry)
    assert isinstance(reg.file_handlers, FileHandlerRegistry)
    assert isinstance(reg.auth, AuthRegistry)
    assert isinstance(reg.search, SearchRegistry)
    assert isinstance(reg.thumbs, ThumbRegistry)
    assert isinstance(reg.db, DbRegistry)
