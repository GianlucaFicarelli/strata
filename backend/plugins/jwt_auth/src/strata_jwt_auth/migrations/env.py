"""Alembic migration environment for strata-jwt-auth.

This ``env.py`` is called by Alembic (via :func:`strata.db.migrations.run_migrations`)
with the application engine injected into ``context.config.attributes["engine"]``.
It configures Alembic to use the async engine synchronously (via ``run_sync``)
and targets only this plugin's metadata so that ``autogenerate`` never touches
tables owned by other plugins.

Running autogenerate from the CLI (for development)::

    cd backend
    # Set the URL so Alembic can connect without the injected engine:
    STRATA_DB_URL="sqlite+aiosqlite:///~/.strata/strata.db" \\
    alembic --config plugins/jwt_auth/src/strata_jwt_auth/migrations/alembic.ini \\
        revision --autogenerate -m "describe your change"
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine
from strata_jwt_auth.models import Base

# Alembic Config object giving access to alembic.ini values.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (URL only, no live connection).

    Used when running ``alembic revision --autogenerate`` from the CLI
    without an injected engine.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Restrict autogenerate to this plugin's tables.
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_sync(conn: Connection) -> None:
    context.configure(
        connection=conn,
        target_metadata=target_metadata,
        # Restrict autogenerate to tables in this plugin's metadata only.
        include_object=lambda obj, name, type_, reflected, compare_to: (
            name in target_metadata.tables if type_ == "table" else True
        ),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using the injected async engine.

    The engine is passed in via ``context.config.attributes["engine"]`` by
    :func:`strata.db.migrations.run_migrations`.  If it is not present (e.g.
    when running from the CLI), fall back to creating a sync engine from the
    configured URL.
    """
    injected: AsyncEngine | None = context.config.attributes.get("engine")  # type: ignore[assignment]

    if injected is not None:
        # Called programmatically from strata.db.migrations.run_migrations.

        async def _run() -> None:
            async with injected.connect() as async_conn:
                await async_conn.run_sync(_do_run_sync)

        asyncio.get_event_loop().run_until_complete(_run())
    else:
        # Called directly via the Alembic CLI.
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _do_run_sync(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
