"""Unit tests for JwtAuthPlugin and PasswordAuthProvider.

No HTTP server needed — tests exercise the plugin class and auth provider
directly.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strata_auth_jwt.models import User
from strata_auth_jwt.plugin import JwtAuthPlugin
from strata_auth_jwt.providers import JwtAuthDbContributor, PasswordAuthProvider
from strata_auth_jwt.utils import hash_password

from strata.db.models import CoreUser
from strata.db.session import session_scope
from strata.plugins.registry import PluginRegistry
from strata.schemas.common import PluginMeta

# ── JwtAuthPlugin.register ────────────────────────────────────────────────────


def test_plugin_registers_db_contributor():
    plugin = JwtAuthPlugin()
    registry = PluginRegistry()
    plugin.register(registry)
    contributors = registry.db.all()
    assert len(contributors) == 1
    assert hasattr(contributors[0], "metadata")
    assert hasattr(contributors[0], "migrations_dir")


def test_plugin_registers_auth_provider():
    plugin = JwtAuthPlugin()
    registry = PluginRegistry()
    plugin.register(registry)
    providers = registry.auth.all()
    assert len(providers) == 1
    assert providers[0].id == "password"


def test_plugin_registers_route_provider():
    plugin = JwtAuthPlugin()
    registry = PluginRegistry()
    plugin.register(registry)
    routers = registry.routes.all_routers()
    assert len(routers) == 1


def test_plugin_describe():
    plugin = JwtAuthPlugin()
    desc = plugin.describe()
    assert isinstance(desc, PluginMeta)
    assert desc.id == "auth_jwt"


def test_plugin_migrations_dir_exists():
    contributor = JwtAuthDbContributor()
    assert contributor.migrations_dir.exists()
    assert (contributor.migrations_dir / "env.py").exists()


# ── PasswordAuthProvider ──────────────────────────────────────────────────────


async def test_password_auth_provider_returns_none_without_credentials(
    session_factory: async_sessionmaker[AsyncSession],
):
    provider = PasswordAuthProvider()
    provider.set_session_factory(session_factory)
    result = await provider.authenticate({})
    assert result is None


async def test_password_auth_provider_returns_none_without_username(
    session_factory: async_sessionmaker[AsyncSession],
):
    provider = PasswordAuthProvider()
    provider.set_session_factory(session_factory)
    result = await provider.authenticate({"password": "secret"})
    assert result is None


async def test_password_auth_provider_raises_401_for_wrong_credentials(
    session_factory: async_sessionmaker[AsyncSession],
):
    async with session_scope(session_factory) as session:
        core = CoreUser()
        session.add(core)
        await session.flush()
        user = User(id=core.id, username="testuser", hashed_password=hash_password("correct"))
        session.add(user)

    provider = PasswordAuthProvider()
    provider.set_session_factory(session_factory)

    with pytest.raises(HTTPException) as exc_info:
        await provider.authenticate({"username": "testuser", "password": "wrong"})
    assert exc_info.value.status_code == 401


async def test_password_auth_provider_returns_auth_user_on_success(
    session_factory: async_sessionmaker[AsyncSession],
):

    async with session_scope(session_factory) as session:
        core = CoreUser()
        session.add(core)
        await session.flush()
        user = User(id=core.id, username="carol", hashed_password=hash_password("pass1234"))
        session.add(user)

    provider = PasswordAuthProvider()
    provider.set_session_factory(session_factory)

    auth_user = await provider.authenticate({"username": "carol", "password": "pass1234"})
    assert auth_user is not None
    assert auth_user.username == "carol"


async def test_password_auth_provider_raises_runtime_error_without_factory():
    provider = PasswordAuthProvider()

    with pytest.raises(RuntimeError, match="session factory"):
        await provider.authenticate({"username": "x", "password": "y"})
