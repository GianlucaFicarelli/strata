"""Integration tests for the /api/files/* endpoints.

A lightweight in-memory ``StorageBackend`` stub is injected via
``app.dependency_overrides`` so no real filesystem or plugin loading is needed.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from strata.dependencies.db import db_session_dep
from strata.dependencies.registry import (
    auth_registry_dep,
    storage_registry_dep,
    storage_template_registry_dep,
)
from strata.main import app
from strata.plugins.protocols import StorageBackend
from strata.plugins.registry import AuthRegistry, StorageRegistry, StorageTemplateRegistry
from strata.schemas.files import FileEntry

# ── In-memory stub backend ────────────────────────────────────────────────────


class _MemoryBackend:
    """Minimal in-memory storage backend for testing."""

    id: str = "mem"
    name: str = "Memory"

    def __init__(self) -> None:
        self._dirs: set[str] = {"/"}
        self._files: dict[str, bytes] = {}

    async def list(self, path: str) -> list[FileEntry]:
        if path not in self._dirs:
            raise HTTPException(status_code=404, detail="Path not found")
        entries: list[FileEntry] = []
        for d in sorted(self._dirs):
            if d in ("/", path):
                continue
            parent = "/".join(d.rstrip("/").split("/")[:-1]) or "/"
            if parent == path:
                entries.append(FileEntry(name=d.split("/")[-1], path=d, is_dir=True))
        for fp in sorted(self._files):
            parent = "/".join(fp.rstrip("/").split("/")[:-1]) or "/"
            if parent == path:
                entries.append(
                    FileEntry(
                        name=fp.split("/")[-1],
                        path=fp,
                        is_dir=False,
                        size=len(self._files[fp]),
                    )
                )
        return entries

    async def read(self, path: str) -> AsyncIterator[bytes]:
        if path not in self._files:
            raise HTTPException(status_code=404, detail="File not found")
        data = self._files[path]

        async def _gen() -> AsyncIterator[bytes]:
            yield data

        return _gen()

    async def write(self, path: str, stream: AsyncIterator[bytes]) -> None:
        chunks: list[bytes] = []
        async for chunk in stream:
            chunks.append(chunk)
        self._files[path] = b"".join(chunks)

    async def delete(self, path: str) -> None:
        if path in self._files:
            del self._files[path]
        elif path in self._dirs:
            self._dirs.discard(path)
        else:
            raise HTTPException(status_code=404, detail="Not found")

    async def mkdir(self, path: str) -> None:
        self._dirs.add(path)

    async def move(self, src: str, dst: str) -> None:
        if src in self._files:
            self._files[dst] = self._files.pop(src)
        elif src in self._dirs:
            self._dirs.discard(src)
            self._dirs.add(dst)

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}


# Protocol conformance check
_: StorageBackend = _MemoryBackend()  # type: ignore[assignment]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mem_backend() -> _MemoryBackend:
    return _MemoryBackend()


@pytest.fixture
def override_storage(mem_backend: _MemoryBackend, db_session: AsyncSession):
    """Override storage, template, auth and db deps for test isolation.

    - Storage registry → single in-memory backend.
    - Template registry → empty (no admin-created instances).
    - Auth registry → empty (no providers → OptionalCurrentUserDep returns None).
    - DB session → shared in-memory test session.

    With an empty template registry and no authenticated user, any backend id
    not found in the static registry will cause a 401 (auth required for
    instance lookup), which is the correct runtime behaviour.
    """
    storage_reg = StorageRegistry()
    storage_reg.add(mem_backend)
    empty_template_reg = StorageTemplateRegistry()
    empty_auth = AuthRegistry()

    app.dependency_overrides[storage_registry_dep] = lambda: storage_reg
    app.dependency_overrides[storage_template_registry_dep] = lambda: empty_template_reg
    app.dependency_overrides[auth_registry_dep] = lambda: empty_auth
    app.dependency_overrides[db_session_dep] = lambda: db_session
    yield
    app.dependency_overrides.pop(storage_registry_dep, None)
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(auth_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)


@pytest.fixture
def http(override_storage) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_list_root_empty(mem_backend: _MemoryBackend, http: AsyncClient):
    async with http as client:
        resp = await client.get("/api/files/list", params={"path": "/", "backend": "mem"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_mkdir_then_list(mem_backend: _MemoryBackend, http: AsyncClient):
    async with http as client:
        r1 = await client.post("/api/files/mkdir", params={"path": "/docs", "backend": "mem"})
        assert r1.status_code == 200
        r2 = await client.get("/api/files/list", params={"path": "/", "backend": "mem"})
    entries = r2.json()
    assert any(e["name"] == "docs" and e["is_dir"] for e in entries)


async def test_upload_then_download(mem_backend: _MemoryBackend, http: AsyncClient):
    async with http as client:
        r1 = await client.post(
            "/api/files/upload",
            params={"path": "/", "backend": "mem"},
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )
        assert r1.status_code == 200
        assert r1.json()["path"] == "/hello.txt"
        r2 = await client.get(
            "/api/files/download", params={"path": "/hello.txt", "backend": "mem"}
        )
    assert r2.status_code == 200
    assert r2.content == b"hello world"


async def test_delete_file(mem_backend: _MemoryBackend, http: AsyncClient):
    mem_backend._files["/target.txt"] = b"bye"
    async with http as client:
        resp = await client.delete(
            "/api/files/delete", params={"path": "/target.txt", "backend": "mem"}
        )
    assert resp.status_code == 200
    assert "/target.txt" not in mem_backend._files


async def test_move_file(mem_backend: _MemoryBackend, http: AsyncClient):
    mem_backend._files["/old.txt"] = b"content"
    async with http as client:
        resp = await client.post(
            "/api/files/move",
            json={"src": "/old.txt", "dst": "/new.txt", "backend": "mem"},
        )
    assert resp.status_code == 200
    assert "/new.txt" in mem_backend._files
    assert "/old.txt" not in mem_backend._files


async def test_list_unknown_backend_unauthenticated_returns_401(override_storage):
    """An unknown backend id with no auth token triggers 401 (instance lookup needs user)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/files/list",
            params={"path": "/", "backend": "nonexistent"},
        )
    assert resp.status_code == 401


async def test_download_missing_file_returns_404(mem_backend: _MemoryBackend, http: AsyncClient):
    async with http as client:
        resp = await client.get(
            "/api/files/download", params={"path": "/ghost.txt", "backend": "mem"}
        )
    assert resp.status_code == 404
