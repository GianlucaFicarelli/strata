"""Strata database layer.

Provides the application-wide async SQLAlchemy engine and session factory.

The engine and ``async_sessionmaker`` are created once in :mod:`strata.main`
during the FastAPI lifespan and stored in ``request.state`` so that:

- Any route or FastAPI ``Depends`` can obtain a session via
  :data:`~strata.dependencies.AsyncSessionDep`.
- Plugins never need to manage their own engines; they only declare their ORM
  models and register their ``MetaData`` (and optional Alembic config path)
  via :class:`~strata.plugins.registry.DbRegistry`.

Usage in a plugin::

    # In the plugin's models.py:
    from strata.db import plugin_base

    Base = plugin_base("strata_myplugin")

    class MyModel(Base):
        __tablename__ = "myplugin_mytable"
        id: Mapped[int] = mapped_column(primary_key=True)
        ...

    # In the plugin's register() method:
    registry.db.add(DbContributor(metadata=Base.metadata))
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path as _Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the application async engine.

    Args:
        url: SQLAlchemy async database URL, e.g.
            ``"sqlite+aiosqlite:///~/.strata/strata.db"`` or
            ``"postgresql+asyncpg://user:pass@host/db"``.
        echo: If ``True``, log all emitted SQL statements.  Avoid in
            production.

    Returns:
        A configured :class:`sqlalchemy.ext.asyncio.AsyncEngine`.
    """
    return create_async_engine(url, echo=echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the application session factory.

    Args:
        engine: The async engine created by :func:`create_engine`.

    Returns:
        An :class:`~sqlalchemy.ext.asyncio.async_sessionmaker` that yields
        :class:`~sqlalchemy.ext.asyncio.AsyncSession` instances with
        ``expire_on_commit=False`` (safe for async use after ``await commit()``).
    """
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Context manager yielding one :class:`~sqlalchemy.ext.asyncio.AsyncSession` per request.

    This is a low-level helper used by the FastAPI ``Depends`` chain in
    :mod:`strata.dependencies`.  Application code should use
    :data:`~strata.dependencies.AsyncSessionDep` instead.

    The session is committed on success and rolled back on any exception,
    then always closed.

    Args:
        session_factory: The application-wide session factory.

    Yields:
        An :class:`~sqlalchemy.ext.asyncio.AsyncSession` scoped to the
        current request.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def plugin_base(plugin_name: str) -> type[DeclarativeBase]:
    """Return a fresh ``DeclarativeBase`` subclass for a plugin.

    Each plugin should call this **once at module level** to obtain its own
    ``Base``, then define all ORM models as subclasses of that ``Base``.
    Using a per-plugin base keeps metadata namespaced and allows the
    :class:`~strata.plugins.registry.DbRegistry` to collect each plugin's
    tables separately.

    The resulting class carries a ``__plugin_name__`` class attribute that
    is used for logging.

    Args:
        plugin_name: Unique plugin identifier, e.g. ``"strata_jwt_auth"``.
            Used only for diagnostics.

    Returns:
        A :class:`~sqlalchemy.orm.DeclarativeBase` subclass whose
        ``metadata`` covers only this plugin's tables.

    Example::

        # strata_myplugin/models.py
        from sqlalchemy.orm import Mapped, mapped_column
        from strata.db import plugin_base

        Base = plugin_base("strata_myplugin")

        class Widget(Base):
            __tablename__ = "myplugin_widget"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str]
    """

    class _Base(DeclarativeBase):
        __plugin_name__: str = plugin_name

    _Base.__name__ = f"{plugin_name}Base"
    _Base.__qualname__ = f"{plugin_name}Base"
    return _Base


class CoreUsersDbContributor:
    """Registers the core ``strata_users`` table and its Alembic migrations.

    This contributor is always added to :class:`~strata.plugins.registry.DbRegistry`
    first, before any plugin's ``register()`` is called.  This guarantees
    that the ``strata_users`` table is created before any plugin migration
    that declares a FK to it.

    Attributes:
        metadata: The SQLAlchemy :class:`~sqlalchemy.MetaData` for
            ``strata_users``.
        migrations_dir: Absolute path to ``strata/db/migrations/`` inside
            the installed ``strata`` package.
    """

    # Import lazily to avoid module-level circular issues during startup.
    @property
    def metadata(self):  # type: ignore[override]
        from strata.db.users import Base  # noqa: PLC0415

        return Base.metadata

    migrations_dir: _Path = _Path(__file__).parent / "migrations"
