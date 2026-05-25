"""Alembic migration helpers for Strata.

:func:`run_migrations` provides a programmatic way to run Alembic ``upgrade
head`` without invoking the CLI.  Each plugin that contributes DB tables
calls this from its ``on_startup()`` hook.

Design constraints
------------------
- Each plugin owns its own Alembic environment (``migrations/`` directory
  inside the plugin package).  This keeps migrations self-contained and
  avoids a central migrations repo that every plugin would need to touch.
- The ``env.py`` in each plugin's ``migrations/`` directory imports the
  plugin's ``Base.metadata`` so that ``autogenerate`` only sees that
  plugin's tables.
- The application engine URL is injected at runtime via
  :func:`run_migrations`, so plugins never hard-code connection strings.

Typical ``env.py`` for a plugin::

    # strata_auth_local/migrations/env.py
    from strata_auth_local.models import Base

    from strata.db.utils import MigrationEnv

    env = MigrationEnv(
        target_metadata=Base.metadata,
        plugin_id="auth_local",
    )
    env.run()
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from alembic import command, context
from alembic.config import Config
from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

L = logging.getLogger(__name__)


class MigrationEnv:
    def __init__(
        self,
        *,
        target_metadata: MetaData,
        plugin_id: str,
    ) -> None:
        self.config: Config = context.config
        self.target_metadata = target_metadata
        self.version_table = f"alembic_version_{plugin_id}"
        self.table_prefix = f"{plugin_id}_"

    def _configure(self, **kwargs: Any) -> None:
        context.configure(
            target_metadata=self.target_metadata,
            version_table=self.version_table,
            # required for SQLite ALTER TABLE support
            render_as_batch=True,
            # Restrict autogenerate to this plugin's tables only.
            # Without this, tables from other plugins or the app appear as
            # "unmapped" and generate spurious drop_table statements.
            include_object=lambda obj, name, type_, reflected, compare_to: (
                name.startswith(self.table_prefix) if name and type_ == "table" else True
            ),
            **kwargs,
        )

    def run_migrations_offline(self) -> None:
        """Run migrations in 'offline' mode.

        This configures the context with just a URL
        and not an Engine, though an Engine is acceptable
        here as well.  By skipping the Engine creation
        we don't even need a DBAPI to be available.

        Calls to context.execute() here emit the given string to the
        script output.

        """
        url = self.config.get_main_option("sqlalchemy.url")
        self._configure(
            url=url,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()

    def do_run_migrations(self, connection: Connection) -> None:
        self._configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()

    async def run_async_migrations(self) -> None:
        injected: AsyncEngine | None = self.config.attributes.get("engine")

        if injected:
            connectable = injected
            async with connectable.connect() as connection:
                await connection.run_sync(self.do_run_migrations)
        else:
            connectable = async_engine_from_config(
                self.config.get_section(self.config.config_ini_section, {}),
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
            )
            async with connectable.connect() as connection:
                await connection.run_sync(self.do_run_migrations)
            await connectable.dispose()

    def run_migrations_online(self) -> None:
        """Run migrations in 'online' mode."""
        asyncio.run(self.run_async_migrations())

    def run(self) -> None:
        if context.is_offline_mode():
            self.run_migrations_offline()
        else:
            self.run_migrations_online()


def version_table_name(plugin_id: str) -> str:
    """Return the Alembic version table name for *plugin_id*.

    Convenience helper used in plugin ``migrations/env.py`` files.

    Args:
        plugin_id: The plugin's entry-point name, e.g. ``"auth_local"``.

    Returns:
        The Alembic version table name e.g. ``"alembic_version_auth_local"``.
    """
    return f"alembic_version_{plugin_id}"


async def run_migrations(engine: AsyncEngine, migrations_dir: Path) -> None:
    """Run ``alembic upgrade head`` programmatically for a plugin.

    The engine is injected into the Alembic ``config.attributes`` dict so
    that the plugin's ``env.py`` can retrieve it without reading a URL from
    ``alembic.ini``.

    Args:
        engine: The application async engine.
        migrations_dir: Absolute path to the plugin's ``migrations/``
            directory (the one containing ``env.py`` and ``versions/``).

    Raises:
        Exception: Propagates any Alembic or SQLAlchemy error so that the
            plugin loader can catch it and skip the plugin.
    """
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_dir))
    # Disable the default URL so env.py uses the injected engine instead.
    alembic_cfg.set_main_option("sqlalchemy.url", "")
    alembic_cfg.attributes["engine"] = engine

    L.info("Running Alembic migrations from %s", migrations_dir)
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    L.info("Migrations complete for %s", migrations_dir.parent.name)
