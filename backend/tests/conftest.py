"""Shared pytest fixtures for the Strata test suite.

All database tests use an in-memory SQLite database that is created fresh
for every test function.  The FastAPI integration tests use httpx's
``ASGITransport`` so no real server is started.

Fixture hierarchy
-----------------
engine → session_factory → db_session   (DB fixtures, function-scoped)
test_app                                 (FastAPI app wired to the in-memory DB)
client                                   (async httpx client against test_app)
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
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


# ── Database fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """In-memory SQLite engine with all core + jwt_auth tables."""
    # Import jwt_auth models so their metadata is registered on Base
    import strata_jwt_auth.models  # noqa: F401

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
async def db_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession]:
    async with session_scope(session_factory) as session:
        yield session


@pytest_asyncio.fixture
async def core_user(db_session: AsyncSession) -> CoreUser:
    """A persisted CoreUser for tests that need an existing user."""
    user = CoreUser()
    db_session.add(user)
    await db_session.flush()
    return user


# ── FastAPI / httpx fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Async HTTP client wired directly to the FastAPI ASGI app.

    The app's full lifespan (including plugin loading and DB migrations)
    runs on entry.  Each test gets a fresh lifespan context.
    """
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
