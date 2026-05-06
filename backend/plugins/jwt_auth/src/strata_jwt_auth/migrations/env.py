"""Alembic migration environment for strata-jwt-auth.

Key design points
-----------------

**Per-plugin version table** (``version_table="alembic_version_jwt_auth"``)
    Alembic's default version table is ``alembic_version``.  When multiple
    plugins share the same database and each runs its own Alembic environment,
    they would all read/write that one table.  The second plugin to run would
    find an unrecognised revision ID from the first plugin and raise::

        alembic.util.exc.CommandError: Can't locate revision identified by '0001'

    Giving each plugin its own ``version_table`` name completely isolates
    their revision histories.  The table is cheap (one row) and the name
    is stable, so there is no downside.

**Branch label** (``branch_labels=("jwt_auth",)`` in the initial revision)
    Alembic supports multiple independent revision *branches* within a single
    ``alembic_version`` table.  We don't use that here because we have
    separate version tables, but the label is kept for clarity when reading
    revision history and for potential future tooling.

**``include_object`` filter**
    Restricts ``alembic revision --autogenerate`` to only compare tables
    registered in *this* plugin's ``Base.metadata``.  Without this, any
    table created by another plugin (or the test suite) would appear as
    "extra" and get a spurious ``drop_table`` in the generated migration.

**Injected vs CLI engine**
    When called programmatically via :func:`strata.db.migrations.run_migrations`,
    the live ``AsyncEngine`` is injected via ``context.config.attributes["engine"]``.
    When run from the CLI (``alembic upgrade head``), that key is absent and
    we fall back to building a sync engine from ``sqlalchemy.url`` in
    ``alembic.ini``.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine
from strata_jwt_auth.models import Base

from strata.db.utils import version_table_name

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Each plugin must use a unique version table so that multiple plugins sharing
# the same database do not overwrite each other's revision pointers.
# Convention: "alembic_version_<plugin_id>".
VERSION_TABLE = version_table_name("jwt_auth")


def _configure_context(connection: Connection) -> None:
    """Apply shared context.configure() options for both online/offline modes."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        # Restrict autogenerate to this plugin's tables only.
        # Without this, tables from other plugins or the app appear as
        # "unmapped" and generate spurious drop_table statements.
        include_object=lambda obj, name, type_, reflected, compare_to: (
            name in target_metadata.tables if type_ == "table" else True
        ),
        # Render AS TIMEZONE-aware columns correctly on PostgreSQL.
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )


def run_migrations_offline() -> None:
    """Run migrations against a URL without a live connection (CLI use)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=lambda obj, name, type_, reflected, compare_to: (
            name in target_metadata.tables if type_ == "table" else True
        ),
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live connection.

    Prefers the ``AsyncEngine`` injected via
    ``context.config.attributes["engine"]`` (set by
    :func:`strata.db.migrations.run_migrations`).  Falls back to a sync
    engine built from the ``sqlalchemy.url`` in ``alembic.ini`` when run
    directly from the CLI.
    """
    injected: AsyncEngine | None = context.config.attributes.get("engine")  # type: ignore[assignment]

    if injected is not None:

        def _run_sync(conn: Connection) -> None:
            _configure_context(conn)
            context.run_migrations()

        async def _run_async() -> None:
            async with injected.connect() as async_conn:
                await async_conn.run_sync(_run_sync)

        asyncio.get_event_loop().run_until_complete(_run_async())
    else:
        # CLI fallback: build a synchronous engine from alembic.ini.
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _configure_context(connection)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
