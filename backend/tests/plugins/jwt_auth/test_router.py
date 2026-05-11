"""Integration tests for strata_jwt_auth.router.

Uses an in-memory SQLite database and a full FastAPI test client.
All DB tables (core + jwt_auth) are created from SQLAlchemy metadata
without running Alembic, which is fast and keeps tests isolated.

Each test gets a fresh in-memory database via the ``engine`` fixture
defined in ``conftest.py``.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.db.session import session_scope
from strata.dependencies import db_session_dep, session_factory_dep
from strata_jwt_auth.router import plugin_router
from strata_jwt_auth.config import settings as jwt_settings


# ── App fixture ───────────────────────────────────────────────────────────────


@pytest.fixture
def jwt_app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    """Minimal FastAPI app with only the jwt_auth router, wired to the test DB."""
    fa = FastAPI()
    fa.include_router(plugin_router)

    # Override session factory so routes use the in-memory DB
    fa.dependency_overrides[session_factory_dep] = lambda: session_factory

    async def _session_dep():
        async with session_scope(session_factory) as s:
            yield s

    fa.dependency_overrides[db_session_dep] = _session_dep
    return fa


@pytest.fixture
def http(jwt_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=jwt_app), base_url="http://test")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _register(client: AsyncClient, username: str = "alice", password: str = "password123"):
    return await client.post(
        "/api/plugins/jwt_auth/register",
        json={"username": username, "password": password},
    )


async def _login(client: AsyncClient, username: str = "alice", password: str = "password123"):
    return await client.post(
        "/api/plugins/jwt_auth/login",
        data={"username": username, "password": password},
    )


# ── Register ──────────────────────────────────────────────────────────────────


async def test_register_creates_user(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "id" in body
    assert "hashed_password" not in body


async def test_register_duplicate_username_returns_409(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        resp = await _register(client)
    assert resp.status_code == 409


async def test_register_short_password_returns_422(http: AsyncClient):
    async with http as client:
        resp = await client.post(
            "/api/plugins/jwt_auth/register",
            json={"username": "bob", "password": "short"},
        )
    assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────


async def test_login_returns_tokens(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        resp = await _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        resp = await _login(client, password="wrong_password")
    assert resp.status_code == 401


async def test_login_unknown_user_returns_401(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        resp = await _login(client, username="nobody")
    assert resp.status_code == 401


# ── /me ───────────────────────────────────────────────────────────────────────


async def test_me_returns_current_user(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]

        resp = await client.get(
            "/api/plugins/jwt_auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


async def test_me_without_token_returns_401(http: AsyncClient):
    async with http as client:
        resp = await client.get("/api/plugins/jwt_auth/me")
    assert resp.status_code == 401


# ── Refresh ───────────────────────────────────────────────────────────────────


async def test_refresh_returns_new_tokens(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        login = await _login(client)
        tokens = login.json()

        resp = await client.post(
            "/api/plugins/jwt_auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens
    # Rotated — new refresh token is issued
    assert "refresh_token" in new_tokens


async def test_refresh_token_can_only_be_used_once(http: AsyncClient, monkeypatch):
    """Refresh token rotation: reusing the same token must fail."""
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        login = await _login(client)
        original_refresh = login.json()["refresh_token"]

        # First use succeeds
        r1 = await client.post(
            "/api/plugins/jwt_auth/refresh",
            json={"refresh_token": original_refresh},
        )
        assert r1.status_code == 200

        # Second use of the same token must fail
        r2 = await client.post(
            "/api/plugins/jwt_auth/refresh",
            json={"refresh_token": original_refresh},
        )
        assert r2.status_code == 401


async def test_refresh_with_invalid_token_returns_401(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        resp = await client.post(
            "/api/plugins/jwt_auth/refresh",
            json={"refresh_token": "bogus_token"},
        )
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


async def test_logout_revokes_refresh_token(http: AsyncClient, monkeypatch):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    async with http as client:
        await _register(client)
        login = await _login(client)
        refresh_token = login.json()["refresh_token"]

        logout = await client.post(
            "/api/plugins/jwt_auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert logout.status_code == 204

        # The revoked token must no longer be usable
        refresh_resp = await client.post(
            "/api/plugins/jwt_auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 401
