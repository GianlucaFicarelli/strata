"""Tests for /api/auth/* routes and session-based auth dependencies."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from strata.api.auth import router as auth_router
from strata.dependencies.auth import _optional_current_user, _require_current_user
from strata.dependencies.registry import auth_registry_dep
from strata.dependencies.storage import storage_backend_dep
from strata.plugins.registry import AuthRegistry
from strata.schemas.auth import AuthUser
from strata.sessions.deps import SessionServiceDep
from strata.sessions.schemas import SessionData
from strata.sessions.service import SessionService


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_auth_registry(*providers: Any) -> AuthRegistry:
    reg = AuthRegistry()
    for p in providers:
        reg.add(p)
    return reg


def _make_app(auth_registry: AuthRegistry) -> FastAPI:
    fa = FastAPI()
    fa.include_router(auth_router)
    fa.dependency_overrides[auth_registry_dep] = lambda: auth_registry
    return fa


def _stub_provider(provider_id: str = "auth_local") -> Any:
    class _Provider:
        id = provider_id
        name = "Test Provider"

        def describe(self) -> dict[str, Any]:
            return {"id": self.id, "name": self.name, "login_url": f"/api/plugins/{self.id}/login"}

    return _Provider()


def _session_data(user_id: str = "uid-123") -> SessionData:
    return SessionData(
        user_id=user_id,
        username="alice",
        display_name="Alice",
        email=None,
        is_admin=False,
    )


# ── GET /api/auth/providers ───────────────────────────────────────────────────


async def test_list_providers_empty():
    app = _make_app(_make_auth_registry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/providers")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_providers_returns_registered_provider():
    app = _make_app(_make_auth_registry(_stub_provider()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "auth_local"
    assert "login_url" in data[0]


# ── GET /api/auth/me ──────────────────────────────────────────────────────────


async def test_me_without_cookie_returns_401():
    """No session cookie → 401."""
    svc = AsyncMock(spec=SessionService)
    svc.get.return_value = None

    app = _make_app(_make_auth_registry())
    app.dependency_overrides[SessionServiceDep] = lambda: svc  # type: ignore[index]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_with_valid_session_returns_user():
    """Valid session cookie → user profile."""
    svc = AsyncMock(spec=SessionService)
    svc.get.return_value = _session_data()

    app = _make_app(_make_auth_registry(_stub_provider()))

    async def _override_session_service():
        return svc

    from strata.sessions import deps as session_deps
    app.dependency_overrides[session_deps._session_service_dep] = _override_session_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Send the session cookie
        c.cookies.set("strata_session", "valid-session-id")
        resp = await c.get("/api/auth/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["display_name"] == "Alice"
    assert body["is_admin"] is False


async def test_me_with_expired_session_returns_401():
    """Session not found in Redis (expired/revoked) → 401."""
    svc = AsyncMock(spec=SessionService)
    svc.get.return_value = None  # Simulates expired/missing session

    app = _make_app(_make_auth_registry())

    from strata.sessions import deps as session_deps
    app.dependency_overrides[session_deps._session_service_dep] = lambda: svc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set("strata_session", "expired-session-id")
        resp = await c.get("/api/auth/me")

    assert resp.status_code == 401


# ── AuthRegistry single-provider constraint ───────────────────────────────────


def test_auth_registry_rejects_second_provider():
    """AuthRegistry must raise RuntimeError when a second provider is added."""
    reg = AuthRegistry()
    reg.add(_stub_provider("auth_local"))
    with pytest.raises(RuntimeError, match="already registered"):
        reg.add(_stub_provider("auth_oidc"))


def test_auth_registry_all_returns_single_item():
    reg = AuthRegistry()
    reg.add(_stub_provider())
    assert len(reg.all()) == 1


def test_auth_registry_all_empty():
    reg = AuthRegistry()
    assert reg.all() == []


def test_auth_registry_get_returns_none_when_empty():
    assert AuthRegistry().get() is None


def test_auth_registry_get_returns_provider():
    reg = AuthRegistry()
    p = _stub_provider()
    reg.add(p)
    assert reg.get() is p
