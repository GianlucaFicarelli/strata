"""Shared pytest fixtures for the Strata test suite."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import strata_auth_jwt.models  # registers auth_jwt ORM models on shared Base  # noqa: F401
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from strata.db.base import Base
from strata.db.models import CoreUser
from strata.db.session import session_scope
from strata.main import app
from strata.plugins.registry import PluginRegistry
from strata.schemas.auth import AuthUser

# ── Database fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """In-memory SQLite engine with all core + auth_jwt tables."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    async with session_scope(session_factory) as session:
        yield session


@pytest_asyncio.fixture
async def core_user(db_session: AsyncSession) -> CoreUser:
    """A persisted CoreUser for tests that need an existing user."""
    user = CoreUser()
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> CoreUser:
    """A persisted CoreUser designated as admin (for auth override use)."""
    user = CoreUser()
    db_session.add(user)
    await db_session.flush()
    return user


# ── AuthUser helpers ──────────────────────────────────────────────────────────


def make_auth_user(core_user: CoreUser, *, username: str = "alice", is_admin: bool = False) -> AuthUser:
    return AuthUser(id=core_user.id, username=username, is_admin=is_admin)


def make_admin_auth_user(core_user: CoreUser, *, username: str = "admin") -> AuthUser:
    return make_auth_user(core_user, username=username, is_admin=True)


# ── FastAPI / httpx fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Async HTTP client wired directly to the FastAPI ASGI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── Plugin registry fixture ───────────────────────────────────────────────────


@pytest.fixture
def plugin_registry() -> PluginRegistry:
    """A clean PluginRegistry with no contributors."""
    return PluginRegistry()
