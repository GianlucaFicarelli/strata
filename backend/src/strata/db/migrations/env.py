"""Alembic migration environment for the Strata core schema.

Manages the ``strata_users`` table.  Uses the same conventions as plugin
migration environments:

- Version table: ``alembic_version_strata_core`` (isolated from plugins).
- Engine injected via ``context.config.attributes["engine"]`` at runtime.
- ``include_object`` filter restricts autogenerate to core tables only.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine

from strata.db.base import Base
from strata.db.utils import version_table_name

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
VERSION_TABLE = version_table_name("strata_core")


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        render_as_batch=True,
        include_object=lambda obj, name, type_, reflected, compare_to: (
            name in target_metadata.tables if type_ == "table" else True
        ),
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        literal_binds=True,
        render_as_batch=True,
        include_object=lambda obj, name, type_, reflected, compare_to: (
            name in target_metadata.tables if type_ == "table" else True
        ),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    injected: AsyncEngine | None = context.config.attributes.get("engine")  # type: ignore[assignment]

    if injected is not None:

        def _run_sync(conn: Connection) -> None:
            _configure(conn)
            context.run_migrations()

        async def _run_async() -> None:
            async with injected.connect() as async_conn:
                await async_conn.run_sync(_run_sync)

        asyncio.get_event_loop().run_until_complete(_run_async())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _configure(connection)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
