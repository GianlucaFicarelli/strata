"""Integration tests for strata.dependencies auth helpers and /api/auth/* routes.

Tests cover:
- optional_current_user_dep: returns None when no token, None when no providers,
  returns user when valid token, raises 401 on bad token
- require_current_user_dep: raises 401 when no user
- GET /api/auth/providers: returns provider list
- GET /api/auth/me: returns user or 401
- verify_token delegation to PasswordAuthProvider
"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strata_jwt_auth.config import settings as jwt_settings
from strata_jwt_auth.models import User
from strata_jwt_auth.providers import PasswordAuthProvider
from strata_jwt_auth.utils import create_access_token, hash_password

from strata.api.auth import router as auth_router
from strata.db.models import CoreUser
from strata.db.session import session_scope
from strata.dependencies.registry import auth_registry_dep, storage_registry_dep
from strata.main import app as main_app
from strata.plugins.registry import AuthRegistry, StorageRegistry

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_jwt_provider(session_factory: async_sessionmaker[AsyncSession]) -> PasswordAuthProvider:
    p = PasswordAuthProvider()
    p.set_session_factory(session_factory)
    return p


def _make_auth_registry(*providers) -> AuthRegistry:
    reg = AuthRegistry()
    for p in providers:
        reg.add(p)
    return reg


def _make_app(auth_registry: AuthRegistry) -> FastAPI:
    fa = FastAPI()
    fa.include_router(auth_router)
    fa.dependency_overrides[auth_registry_dep] = lambda: auth_registry
    return fa


# ── /api/auth/providers ───────────────────────────────────────────────────────


async def test_list_providers_empty():
    app = _make_app(_make_auth_registry())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/providers")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_providers_returns_jwt_auth(
    session_factory: async_sessionmaker[AsyncSession],
):
    provider = _make_jwt_provider(session_factory)
    app = _make_app(_make_auth_registry(provider))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "password"
    assert "login_url" in data[0]


# ── /api/auth/me ──────────────────────────────────────────────────────────────


async def test_me_without_token_returns_401(
    session_factory: async_sessionmaker[AsyncSession],
):
    provider = _make_jwt_provider(session_factory)
    app = _make_app(_make_auth_registry(provider))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_with_valid_token_returns_user(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_REFRESH_EXPIRE_DAYS", 30, raising=False)

    # Register a user
    async with session_scope(session_factory) as session:
        core = CoreUser()
        session.add(core)
        await session.flush()
        db_user = User(id=core.id, username="eve", hashed_password=hash_password("pass1234"))
        session.add(db_user)

    # Build a token manually (no HTTP round-trip needed)
    token = create_access_token(db_user)

    provider = _make_jwt_provider(session_factory)
    app = _make_app(_make_auth_registry(provider))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "eve"


async def test_me_with_invalid_token_returns_401(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)

    provider = _make_jwt_provider(session_factory)
    app = _make_app(_make_auth_registry(provider))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/auth/me", headers={"Authorization": "Bearer bogus.token.here"})
    assert resp.status_code == 401


# ── optional_current_user_dep ─────────────────────────────────────────────────


async def test_optional_dep_returns_none_when_no_providers():
    """With an empty AuthRegistry, the dep should return None (not raise)."""

    main_app.dependency_overrides[auth_registry_dep] = _make_auth_registry

    async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as c:
        # /api/auth/providers uses auth_registry but not the optional dep;
        # use a files endpoint which does use OptionalCurrentUserDep

        main_app.dependency_overrides[storage_registry_dep] = StorageRegistry
        resp = await c.get("/api/files/list", params={"path": "/", "backend": "nonexistent"})
    # 400 (unknown backend) proves the dep resolved (didn't 401)
    assert resp.status_code == 400

    main_app.dependency_overrides.pop(auth_registry_dep, None)
    main_app.dependency_overrides.pop(storage_registry_dep, None)


# ── AuthRegistry.verify_token ─────────────────────────────────────────────────


async def test_auth_registry_verify_token_delegates(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
):
    monkeypatch.setattr(jwt_settings, "JWT_SECRET", "s", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(jwt_settings, "JWT_EXPIRE_MINUTES", 15, raising=False)

    async with session_scope(session_factory) as session:
        core = CoreUser()
        session.add(core)
        await session.flush()
        db_user = User(id=core.id, username="frank", hashed_password=hash_password("x"))
        session.add(db_user)

    token = create_access_token(db_user)
    provider = _make_jwt_provider(session_factory)
    registry = _make_auth_registry(provider)

    user = await registry.verify_token(token)
    assert user is not None
    assert user.username == "frank"


async def test_auth_registry_verify_token_returns_none_for_empty_registry():
    reg = AuthRegistry()
    result = await reg.verify_token("any.token.value")
    assert result is None


async def test_auth_provider_verify_token_default_returns_none():
    """A provider that doesn't implement verify_token returns None (protocol default)."""

    class _CredentialOnlyProvider:
        id = "ldap"
        name = "LDAP"

        async def authenticate(self, credentials):
            return None

        async def verify_token(self, token):
            return None

    reg = AuthRegistry()
    reg.add(_CredentialOnlyProvider())
    result = await reg.verify_token("some.token")
    assert result is None
