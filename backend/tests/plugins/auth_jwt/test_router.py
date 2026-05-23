"""Integration tests for strata_auth_jwt.router.

Uses an in-memory SQLite database and a full FastAPI test client.
All DB tables (core + auth_jwt) are created from SQLAlchemy metadata
without running Alembic, which is fast and keeps tests isolated.

Cookie behaviour
----------------
The refresh token is delivered as an HttpOnly cookie named
``strata_refresh_token``.  httpx's ``AsyncClient`` stores cookies
automatically, so a login followed by a refresh call will send the
cookie without any manual plumbing — exactly as a real browser would.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strata_auth_jwt.router import _REFRESH_COOKIE, plugin_router

from strata.db.session import session_scope
from strata.dependencies.db import db_session_dep, session_factory_dep

# ── App fixture ───────────────────────────────────────────────────────────────


@pytest.fixture
def jwt_app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    """Minimal FastAPI app with only the auth_jwt router, wired to the test DB."""
    fa = FastAPI()
    fa.include_router(plugin_router)
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


async def _register(
    client: AsyncClient,
    username: str = "alice",
    password: str = "password123",
):
    return await client.post(
        "/api/plugins/auth_jwt/register",
        json={"username": username, "password": password},
    )


async def _login(
    client: AsyncClient,
    username: str = "alice",
    password: str = "password123",
):
    return await client.post(
        "/api/plugins/auth_jwt/login",
        data={"username": username, "password": password},
    )


# ── Register ──────────────────────────────────────────────────────────────────


async def test_register_creates_user(http: AsyncClient):
    async with http as client:
        resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "id" in body
    assert "hashed_password" not in body


async def test_register_duplicate_username_returns_409(http: AsyncClient):
    async with http as client:
        await _register(client)
        resp = await _register(client)
    assert resp.status_code == 409


async def test_register_short_password_returns_422(http: AsyncClient):
    async with http as client:
        resp = await client.post(
            "/api/plugins/auth_jwt/register",
            json={"username": "bob", "password": "short"},
        )
    assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────


async def test_login_returns_access_token(http: AsyncClient):
    async with http as client:
        await _register(client)
        resp = await _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert "expires_in" in body
    # Refresh token must NOT be in the body — it lives in the HttpOnly cookie.
    assert "refresh_token" not in body


async def test_login_sets_httponly_refresh_cookie(http: AsyncClient):
    async with http as client:
        await _register(client)
        resp = await _login(client)
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert _REFRESH_COOKIE in set_cookie
    assert "httponly" in set_cookie.lower()


async def test_login_wrong_password_returns_401(http: AsyncClient):
    async with http as client:
        await _register(client)
        resp = await _login(client, password="wrong_password")
    assert resp.status_code == 401


async def test_login_unknown_user_returns_401(http: AsyncClient):
    async with http as client:
        resp = await _login(client, username="nobody")
    assert resp.status_code == 401


# ── /me ───────────────────────────────────────────────────────────────────────


async def test_me_returns_current_user(http: AsyncClient):
    async with http as client:
        await _register(client)
        login_resp = await _login(client)
        token = login_resp.json()["access_token"]
        resp = await client.get(
            "/api/plugins/auth_jwt/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


async def test_me_without_token_returns_401(http: AsyncClient):
    async with http as client:
        resp = await client.get("/api/plugins/auth_jwt/me")
    assert resp.status_code == 401


# ── Refresh ───────────────────────────────────────────────────────────────────


async def test_refresh_returns_new_access_token(http: AsyncClient):
    """httpx stores the Set-Cookie from login automatically; refresh sends it."""
    async with http as client:
        await _register(client)
        await _login(client)
        resp = await client.post("/api/plugins/auth_jwt/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    # Refresh token stays in the cookie, never in the body.
    assert "refresh_token" not in body


async def test_refresh_rotates_cookie(http: AsyncClient):
    """Each refresh must issue a fresh cookie (token rotation)."""
    async with http as client:
        await _register(client)
        await _login(client)

        r1 = await client.post("/api/plugins/auth_jwt/refresh")
        cookie_after_first = client.cookies.get(_REFRESH_COOKIE)

        r2 = await client.post("/api/plugins/auth_jwt/refresh")
        cookie_after_second = client.cookies.get(_REFRESH_COOKIE)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert cookie_after_first != cookie_after_second


async def test_refresh_without_cookie_returns_401(http: AsyncClient):
    async with http as client:
        resp = await client.post("/api/plugins/auth_jwt/refresh")
    assert resp.status_code == 401


async def test_refresh_token_can_only_be_used_once(http: AsyncClient):
    """Token rotation: after one refresh the old cookie value must be rejected."""
    async with http as client:
        await _register(client)
        await _login(client)

        # Capture the cookie value before the first refresh.
        original_cookie = client.cookies.get(_REFRESH_COOKIE)

        # First refresh — succeeds, rotates the cookie.
        r1 = await client.post("/api/plugins/auth_jwt/refresh")
        assert r1.status_code == 200

        # Forcibly restore the old (now revoked) cookie value.
        client.cookies.set(_REFRESH_COOKIE, original_cookie)

        # Second use of the original cookie must fail.
        r2 = await client.post("/api/plugins/auth_jwt/refresh")
        assert r2.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


async def test_logout_revokes_refresh_token(http: AsyncClient):
    async with http as client:
        await _register(client)
        await _login(client)

        logout_resp = await client.post("/api/plugins/auth_jwt/logout")
        assert logout_resp.status_code == 204

        # Cookie was cleared — refresh must now fail.
        resp = await client.post("/api/plugins/auth_jwt/refresh")
        assert resp.status_code == 401


async def test_logout_clears_cookie(http: AsyncClient):
    async with http as client:
        await _register(client)
        await _login(client)
        assert client.cookies.get(_REFRESH_COOKIE) is not None

        logout_resp = await client.post("/api/plugins/auth_jwt/logout")
        assert logout_resp.status_code == 204

    # delete_cookie sets Max-Age=0; httpx removes the cookie from the jar.
    assert http.cookies.get(_REFRESH_COOKIE) is None


async def test_logout_without_cookie_is_idempotent(http: AsyncClient):
    """Logout with no cookie must succeed silently — nothing to revoke."""
    async with http as client:
        resp = await client.post("/api/plugins/auth_jwt/logout")
    assert resp.status_code == 204
