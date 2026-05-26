"""Integration tests for /api/files/* endpoints.

A lightweight in-memory StorageBackend stub is injected via
``app.dependency_overrides`` so no real filesystem or plugin loading is needed.

``storage_backend_dep`` is overridden to return the stub unconditionally —
bypassing the UUID lookup.  The ``?backend`` query param is still required by
FastAPI but its value is ignored by this override.

The download endpoint uses a signed HMAC token (not the session cookie), so
tests for it use ``issue_download_token`` directly to generate valid tokens.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from strata.db.models import CoreUser
from strata.dependencies.auth import _require_current_user
from strata.dependencies.db import db_session_dep
from strata.dependencies.registry import auth_registry_dep, storage_template_registry_dep
from strata.dependencies.storage import storage_backend_dep
from strata.main import app
from strata.plugins.registry import AuthRegistry, StorageTemplateRegistry
from strata.schemas.common import StorageMeta
from strata.schemas.files import FileEntry
from strata.storage import service as storage_service
from strata.tokens import issue_download_token
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
    """Override all file-API deps for the session-authenticated endpoints."""
    user = make_auth_user(core_user, username="alice")
    empty_template_reg = StorageTemplateRegistry()
    empty_auth = AuthRegistry()

    app.dependency_overrides[storage_backend_dep] = lambda: mem_backend
    app.dependency_overrides[storage_template_registry_dep] = lambda: empty_template_reg
    app.dependency_overrides[auth_registry_dep] = lambda: empty_auth
    app.dependency_overrides[db_session_dep] = lambda: db_session
    app.dependency_overrides[_require_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(storage_backend_dep, None)
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(auth_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)
    app.dependency_overrides.pop(_require_current_user, None)


@pytest.fixture
def override_download(
    db_session: AsyncSession,
    core_user: CoreUser,
):
    """Override the minimal deps needed by the token-authenticated download endpoints.

    Does not set storage_backend_dep or _require_current_user — the download
    path authenticates via an HMAC token and resolves the backend itself via
    resolve_backend_for_user.
    """
    empty_template_reg = StorageTemplateRegistry()

    app.dependency_overrides[storage_template_registry_dep] = lambda: empty_template_reg
    app.dependency_overrides[db_session_dep] = lambda: db_session
    yield
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)


@pytest.fixture
def override_unknown_backend(
    db_session: AsyncSession,
    core_user: CoreUser,
):
    """Override deps for the unknown-backend test (session auth, no storage stub)."""
    user = make_auth_user(core_user, username="alice")
    empty_template_reg = StorageTemplateRegistry()

    app.dependency_overrides[storage_template_registry_dep] = lambda: empty_template_reg
    app.dependency_overrides[db_session_dep] = lambda: db_session
    app.dependency_overrides[_require_current_user] = lambda: user
    yield
    app.dependency_overrides.pop(storage_template_registry_dep, None)
    app.dependency_overrides.pop(db_session_dep, None)
    app.dependency_overrides.pop(_require_current_user, None)


@pytest_asyncio.fixture
async def http(override_storage) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def http_download(override_download) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def http_no_backend(override_unknown_backend) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── Basic file operations ──────────────────────────────────────────────────────


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


async def test_upload_then_list(http: AsyncClient):
    r1 = await http.post(
        "/api/files/upload",
        params={"path": "/", "backend": "mem"},
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert r1.status_code == 200
    assert r1.json()["path"] == "/hello.txt"
    r2 = await http.get("/api/files/list", params={"path": "/", "backend": "mem"})
    names = [e["name"] for e in r2.json()]
    assert "hello.txt" in names


async def test_delete_file(mem_backend: _MemoryBackend, http: AsyncClient):
    mem_backend._files["/target.txt"] = b"bye"
    resp = await http.delete("/api/files/delete", params={"path": "/target.txt", "backend": "mem"})
    assert resp.status_code == 200
    assert "/target.txt" not in mem_backend._files


async def test_move_file(mem_backend: _MemoryBackend, http: AsyncClient):
    mem_backend._files["/old.txt"] = b"content"
    resp = await http.post(
        "/api/files/move",
        params={"backend": "mem"},
        json={"src": "/old.txt", "dst": "/new.txt"},
    )
    assert resp.status_code == 200
    assert "/new.txt" in mem_backend._files
    assert "/old.txt" not in mem_backend._files


# ── Download token flow ────────────────────────────────────────────────────────


async def test_get_download_token_returns_token(
    http: AsyncClient,
    core_user: CoreUser,
    monkeypatch,
):
    """Authenticated request to /download-token returns a signed token."""
    monkeypatch.setattr(
        "strata.tokens.settings.ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ="
    )
    resp = await http.get(
        "/api/files/download-token",
        params={"backend": "some-uuid"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert "expires_in" in body
    assert body["expires_in"] > 0


async def test_download_with_valid_token(
    mem_backend: _MemoryBackend,
    core_user: CoreUser,
    http_download: AsyncClient,
    monkeypatch,
):
    """A valid HMAC token lets the download proceed without a session cookie."""
    monkeypatch.setattr(
        "strata.tokens.settings.ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ="
    )

    mem_backend._files["/secret.txt"] = b"classified"
    token = issue_download_token(user_id=core_user.id, backend_id="mem")

    # Patch resolve_backend_for_user so the download endpoint can find the
    # in-memory backend without a real DB instance row.
    async def _fake_resolve(db, instance_id, user_id, username, template_registry):
        return mem_backend

    monkeypatch.setattr(storage_service, "resolve_backend_for_user", _fake_resolve)

    resp = await http_download.get(
        "/api/files/download",
        params={"path": "/secret.txt", "token": token},
    )
    assert resp.status_code == 200, resp.text
    assert resp.content == b"classified"


async def test_download_with_invalid_token_returns_401(
    http_download: AsyncClient,
    monkeypatch,
):
    """A tampered or missing token returns 401."""
    monkeypatch.setattr(
        "strata.tokens.settings.ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ="
    )
    resp = await http_download.get(
        "/api/files/download",
        params={"path": "/secret.txt", "token": "not.a.valid.token"},
    )
    assert resp.status_code == 401


# ── Unknown backend ────────────────────────────────────────────────────────────


async def test_unknown_backend_returns_400(http_no_backend: AsyncClient):
    """An unknown instance UUID with an authenticated user returns 400."""
    resp = await http_no_backend.get(
        "/api/files/list",
        params={"path": "/", "backend": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 400
