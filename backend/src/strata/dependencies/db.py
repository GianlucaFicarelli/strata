"""Database dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from strata.db.session import session_scope


def session_factory_dep(request: Request) -> async_sessionmaker[AsyncSession]:
    """Extract the session factory from ``request.state``."""
    return request.state.db_session_factory


async def db_session_dep(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(session_factory_dep)],
) -> AsyncGenerator[AsyncSession]:
    """Yield one :class:`~sqlalchemy.ext.asyncio.AsyncSession` per request.

    Commits on success, rolls back on any unhandled exception.
    """
    async with session_scope(session_factory) as session:
        yield session


AsyncSessionDep = Annotated[AsyncSession, Depends(db_session_dep, scope="function")]
