"""Unit tests for strata.db.session.session_scope."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.db.models import CoreUser
from strata.db.session import session_scope


async def test_session_scope_commits_on_success(
    session_factory: async_sessionmaker[AsyncSession],
):
    """A successful block should persist rows."""
    async with session_scope(session_factory) as session:
        user = CoreUser()
        session.add(user)

    # Re-open a session to verify the row persisted
    async with session_scope(session_factory) as session:
        result = await session.execute(select(CoreUser))
        users = result.scalars().all()
    assert len(users) == 1


async def test_session_scope_rolls_back_on_exception(
    session_factory: async_sessionmaker[AsyncSession],
):
    """An exception inside the block should roll back the transaction."""
    with pytest.raises(ValueError):
        async with session_scope(session_factory) as session:
            session.add(CoreUser())
            raise ValueError("intentional failure")

    # Nothing should have been persisted
    async with session_scope(session_factory) as session:
        result = await session.execute(select(CoreUser))
        users = result.scalars().all()
    assert users == []


async def test_session_scope_yields_async_session(
    session_factory: async_sessionmaker[AsyncSession],
):
    async with session_scope(session_factory) as session:
        assert isinstance(session, AsyncSession)
