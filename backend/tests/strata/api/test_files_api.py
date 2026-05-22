"""Integration tests for the /api/files/* endpoints.

A lightweight in-memory ``StorageBackend`` stub is injected via
``app.dependency_overrides`` so no real filesystem or plugin loading is needed.

``StorageBackendDep`` is overridden directly with a lambda that returns the
stub — bypassing instance UUID lookup entirely, which is tested separately in
``test_service.py`` and ``test_admin_api.py``.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from strata.db.models import CoreUser
from strata.dependencies.auth import require_current_user_dep
from strata.dependencies.db import db_session_dep
from strata.dependencies.registry import auth_registry_dep, storage_template_registry_dep
from strata.dependencies.storage import storage_backend_dep
from strata.main import app
from strata.plugins.protocols import StorageBackend
from strata.plugins.registry import AuthRegistry, StorageTemplateRegistry
from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry
from tests.conftest import make_auth_user

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

    def describe(self) -> StorageMeta:
        return StorageMeta(id=self.id, name=self.name)


# Protocol conformance check
_: StorageBackend = _MemoryBackend()  # type: ignore[assignment]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mem_backend() -> _MemoryBackend:
    return _MemoryBackend()


@pytest.fixture
def override_storage(
    mem_backend: _MemoryBackend,
    db_session: AsyncSession,
    core_user: CoreUser,
):
    """Override deps for test isolation.

    - ``storage_backend_dep`` → returns the in-memory stub unconditionally,
      bypassing UUID lookup.  The ``?backend`` query param is still required
      by FastAPI but its value is ignored by this override.
    - ``storage_template_registry_dep`` → empty registry (no templates needed).
    - ``auth_registry_dep`` → empty (no auth providers).
    - ``require_current_user_dep`` → fixed AuthUser (alice).
    - ``db_session_dep`` → shared in-memory test session.
    """
    empty_template_reg = StorageTemplateRegistry()
    empty_auth = AuthRegistry()
    user = make_auth_user(core_user, username="alice")

    app.dependency_overrides[storage_backend_dep] = lambda: mem_backend
    app.dependency_overrides[storage_template_registry_dep] = lambda: empty_template_reg
    app.dependency_overrides[auth_registry_dep] = lambda: empty_auth
    app.dependency_overrides[db_session_dep] = lambda: db_session
    app.dependency_overrides[require_current_user_dep] = lambda: user
    yield
    app.dependency_overrides.pop(storage_backend_dep, None)
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(auth_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)
    app.dependency_overrides.pop(require_current_user_dep, None)


@pytest_asyncio.fixture
async def http(override_storage) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_list_root_empty(http: AsyncClient):
    resp = await http.get("/api/files/list", params={"path": "/", "backend": "mem"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_mkdir_then_list(http: AsyncClient):
    r1 = await http.post("/api/files/mkdir", params={"path": "/docs", "backend": "mem"})
    assert r1.status_code == 200
    r2 = await http.get("/api/files/list", params={"path": "/", "backend": "mem"})
    entries = r2.json()
    assert any(e["name"] == "docs" and e["is_dir"] for e in entries)


async def test_upload_then_download(http: AsyncClient):
    r1 = await http.post(
        "/api/files/upload",
        params={"path": "/", "backend": "mem"},
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert r1.status_code == 200
    assert r1.json()["path"] == "/hello.txt"
    r2 = await http.get("/api/files/download", params={"path": "/hello.txt", "backend": "mem"})
    assert r2.status_code == 200
    assert r2.content == b"hello world"


async def test_delete_file(mem_backend: _MemoryBackend, http: AsyncClient):
    mem_backend._files["/target.txt"] = b"bye"
    resp = await http.delete("/api/files/delete", params={"path": "/target.txt", "backend": "mem"})
    assert resp.status_code == 200
    assert "/target.txt" not in mem_backend._files


async def test_move_file(mem_backend: _MemoryBackend, http: AsyncClient):
    mem_backend._files["/old.txt"] = b"content"
    # backend is a query param; FileMoveRequest body only carries src + dst
    resp = await http.post(
        "/api/files/move",
        params={"backend": "mem"},
        json={"src": "/old.txt", "dst": "/new.txt"},
    )
    assert resp.status_code == 200
    assert "/new.txt" in mem_backend._files
    assert "/old.txt" not in mem_backend._files


async def test_unknown_backend_returns_400(
    db_session: AsyncSession,
    core_user: CoreUser,
):
    """An unknown instance UUID with an authenticated user returns 400."""
    user = make_auth_user(core_user, username="alice")
    empty_template_reg = StorageTemplateRegistry()

    app.dependency_overrides[storage_template_registry_dep] = lambda: empty_template_reg
    app.dependency_overrides[db_session_dep] = lambda: db_session
    app.dependency_overrides[require_current_user_dep] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/files/list",
                params={"path": "/", "backend": "00000000-0000-0000-0000-000000000000"},
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(storage_template_registry_dep, None)
        app.dependency_overrides.pop(db_session_dep, None)
        app.dependency_overrides.pop(require_current_user_dep, None)


async def test_download_missing_file_returns_404(mem_backend: _MemoryBackend, http: AsyncClient):
    resp = await http.get("/api/files/download", params={"path": "/ghost.txt", "backend": "mem"})
    assert resp.status_code == 404
